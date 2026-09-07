"""Transcricao via faster-whisper, com timestamp por palavra.

Nao e mais o transcriber default do pipeline: o timestamp por palavra do Whisper vem da
cross-attention do proprio decoder, com erro tipico de 200-300ms, e legenda em karaoke e
o consumidor mais sensivel a isso que existe. O default passou a ser o WhisperX, que
realinha por CTC (ver `clipador.transcribe.whisperx_transcriber`). Este continua como
fallback: nao precisa de modelo de alinhamento por idioma e roda onde o WhisperX nao
instala.

Os parametros de decodificacao aqui deixaram de ser os defaults da lib. Os tres que mais
mudam o resultado em PT-BR:

- `condition_on_previous_text=False`: com o default `True`, o modelo alimenta a propria
  saida anterior como contexto e, num trecho de silencio ou musica, entra em loop
  repetindo a ultima frase. Desligar custa um pouco de coerencia de contexto longo e
  elimina a classe inteira de alucinacao por repeticao.
- `beam_size=5`: busca em feixe em vez de guloso. Mais lento, mede menos erro de nome
  proprio e de concordancia.
- `initial_prompt`/`hotwords`: vocabulario de dominio vindo da KB do projeto, ver
  `clipador.transcribe.vocabulary`.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Callable

from clipador.transcribe.diarize import Diarizer, NullDiarizer
from clipador.transcribe.models import (
    Segment,
    TranscriptionResult,
    Word,
    renumber_words,
)
from clipador.transcribe.normalize import NormalizationRules, normalize_transcription
from clipador.transcribe.vocabulary import Vocabulary

# Fallback de temperatura do Whisper: quando a saida numa temperatura falha os limiares
# abaixo, ele redecodifica na proxima. E o mecanismo padrao anti-alucinacao da referencia
# original do Whisper, que o faster-whisper implementa mas so usa se a tupla for passada.
DEFAULT_TEMPERATURES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
# Razao de compressao acima da qual a saida e considerada texto repetitivo (loop).
DEFAULT_COMPRESSION_RATIO_THRESHOLD = 2.4
DEFAULT_NO_SPEECH_THRESHOLD = 0.6
# O VAD do Silero corta em silencio; com o minimo muito baixo ele fatia dentro da palavra
# e come o ataque da consoante. 500ms e o piso seguro para fala continua.
DEFAULT_VAD_PARAMETERS = {"min_silence_duration_ms": 500, "speech_pad_ms": 200}


def _attr(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def build_result(
    raw_segments: Iterable[Any],
    info: Any = None,
    audio_path: str | Path | None = None,
    normalization: NormalizationRules | None = NormalizationRules(),
) -> TranscriptionResult:
    """Converte a saida do faster-whisper no schema estavel do projeto, ja normalizada."""
    segments: list[Segment] = []
    for raw_segment in raw_segments:
        words = [
            Word(
                id=0,
                text=str(_attr(raw_word, "word", _attr(raw_word, "text", ""))).strip(),
                start=float(_attr(raw_word, "start", 0.0)),
                end=float(_attr(raw_word, "end", 0.0)),
            )
            for raw_word in (_attr(raw_segment, "words") or [])
        ]
        segments.append(
            Segment(
                id=0,
                start=float(_attr(raw_segment, "start", 0.0)),
                end=float(_attr(raw_segment, "end", 0.0)),
                text=str(_attr(raw_segment, "text", "")).strip(),
                words=words,
            )
        )

    renumber_words(segments)
    result = TranscriptionResult(
        segments=segments,
        language=_attr(info, "language"),
        duration=_attr(info, "duration"),
        audio_path=None if audio_path is None else str(audio_path),
    )
    return result if normalization is None else normalize_transcription(result, normalization)


def supports_hotwords(transcribe_callable: Any) -> bool:
    """`hotwords` so existe no faster-whisper recente. Checar a assinatura evita um
    TypeError em instalacao mais antiga sem precisar fixar versao minima no pyproject."""
    try:
        parameters = inspect.signature(transcribe_callable).parameters
    except (TypeError, ValueError):
        return False
    return "hotwords" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )


class FasterWhisperTranscriber:
    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "auto",
        compute_type: str = "default",
        language: str | None = "pt",
        vad_filter: bool = True,
        beam_size: int = 5,
        vocabulary: Vocabulary | None = None,
        normalization: NormalizationRules | None = NormalizationRules(),
        diarizer: Diarizer | None = None,
        model_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.vad_filter = vad_filter
        self.beam_size = beam_size
        self.vocabulary = vocabulary or Vocabulary()
        self.normalization = normalization
        self.diarizer: Diarizer = diarizer or NullDiarizer()
        self._model_factory = model_factory or self._load_default_model
        self._model: Any | None = None

    def _load_default_model(self) -> Any:
        from faster_whisper import WhisperModel

        return WhisperModel(
            self.model_size, device=self.device, compute_type=self.compute_type
        )

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = self._model_factory()
        return self._model

    def _decode_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {
            "word_timestamps": True,
            "language": self.language,
            "vad_filter": self.vad_filter,
            "beam_size": self.beam_size,
            "condition_on_previous_text": False,
            "temperature": DEFAULT_TEMPERATURES,
            "compression_ratio_threshold": DEFAULT_COMPRESSION_RATIO_THRESHOLD,
            "no_speech_threshold": DEFAULT_NO_SPEECH_THRESHOLD,
        }
        if self.vad_filter:
            options["vad_parameters"] = dict(DEFAULT_VAD_PARAMETERS)
        if self.vocabulary.initial_prompt:
            options["initial_prompt"] = self.vocabulary.initial_prompt
        if self.vocabulary.hotwords and supports_hotwords(self.model.transcribe):
            options["hotwords"] = self.vocabulary.hotwords
        return options

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        raw_segments, info = self.model.transcribe(str(audio_path), **self._decode_options())
        result = build_result(raw_segments, info, audio_path, self.normalization)
        return self.diarizer.assign(result, audio_path)
