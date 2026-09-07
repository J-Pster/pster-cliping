"""Transcrição alternativa via WhisperX: faster-whisper + alinhamento forçado CTC + pyannote.

WhisperX usa faster-whisper por baixo, mas troca os timestamps por cross-attention do
Whisper por um alinhamento forçado com wav2vec2 (CTC). Na prática o erro de timestamp por
palavra cai para a casa dos milissegundos, o que importa direto para o efeito karaokê das
legendas. Em troca, carrega um modelo extra de alinhamento por idioma.

Fluxo oficial da lib, reproduzido em `WhisperXTranscriber.transcribe`:

1. `whisperx.load_model(...)` -> modelo ASR (faster-whisper)
2. `whisperx.load_audio(path)` -> waveform 16kHz reutilizada em todas as etapas
3. `model.transcribe(audio, batch_size=...)` -> `{"segments": [...], "language": "pt"}`
4. `whisperx.load_align_model(language_code=...)` + `whisperx.align(...)` -> palavras alinhadas
5. opcional: `whisperx.diarize.DiarizationPipeline(token=...)` +
   `whisperx.assign_word_speakers(diarize_segments, aligned)` -> campo `speaker`

Diarização real exige `hf_token` (token HuggingFace) E o aceite manual dos termos dos
modelos `pyannote/speaker-diarization-3.1` e `pyannote/segmentation-3.0` na conta do
HuggingFace. Sem token, `diarize=True` emite um aviso e a transcrição segue sem speaker
(equivalente ao `NullDiarizer`), em vez de falhar.
"""

from __future__ import annotations

import logging
import time
import warnings
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

logger = logging.getLogger(__name__)


def _as_float(value: Any, fallback: float) -> float:
    return fallback if value is None else float(value)


def supported_asr_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Filtra `asr_options` pelos campos que a versao instalada do faster-whisper aceita.

    O WhisperX repassa o dicionario inteiro para `faster_whisper.transcribe.
    TranscriptionOptions(**options)`; uma chave que aquela versao nao conhece (`hotwords`
    e a recente) levanta TypeError no carregamento do modelo. Filtrar aqui deixa o
    vocabulario funcionar no que da, em vez de fixar uma versao minima no pyproject por
    causa de um parametro opcional.
    """
    try:
        from faster_whisper.transcribe import TranscriptionOptions

        allowed = set(getattr(TranscriptionOptions, "_fields", ())) or set(
            getattr(TranscriptionOptions, "__annotations__", {})
        )
    except Exception:  # pragma: no cover - so acontece sem faster-whisper instalado
        allowed = {"initial_prompt"}
    if not allowed:
        allowed = {"initial_prompt"}
    dropped = sorted(set(options) - allowed)
    if dropped:
        logger.info("asr_options ignoradas nesta versao do faster-whisper: %s", dropped)
    return {key: value for key, value in options.items() if key in allowed}


def build_result_from_whisperx(
    raw_segments: Iterable[Mapping[str, Any]],
    language: str | None = None,
    audio_path: str | Path | None = None,
    normalization: NormalizationRules | None = NormalizationRules(),
) -> TranscriptionResult:
    """Converte a saída alinhada do WhisperX no mesmo schema estável do projeto."""
    segments: list[Segment] = []
    for raw_segment in raw_segments:
        segment_start = _as_float(raw_segment.get("start"), 0.0)
        segment_end = _as_float(raw_segment.get("end"), segment_start)
        # Palavras sem fonema alinhável (números, símbolos) voltam do CTC sem start/end.
        cursor = segment_start
        words: list[Word] = []
        for raw_word in raw_segment.get("words") or []:
            start = _as_float(raw_word.get("start"), cursor)
            end = _as_float(raw_word.get("end"), start)
            cursor = end
            words.append(
                Word(
                    id=0,
                    text=str(raw_word.get("word", "")).strip(),
                    start=start,
                    end=end,
                    speaker=raw_word.get("speaker"),
                )
            )
        segments.append(
            Segment(
                id=0,
                start=segment_start,
                end=segment_end,
                text=str(raw_segment.get("text", "")).strip(),
                words=words,
                speaker=raw_segment.get("speaker"),
            )
        )

    renumber_words(segments)
    result = TranscriptionResult(
        segments=segments,
        language=language,
        duration=max((s.end for s in segments), default=None),
        audio_path=None if audio_path is None else str(audio_path),
    )
    return result if normalization is None else normalize_transcription(result, normalization)


class WhisperXTranscriber:
    """Transcriber alternativo ao `FasterWhisperTranscriber`, com alinhamento CTC.

    Mesmo contrato (`Transcriber`): `transcribe(audio_path) -> TranscriptionResult`.

    Args:
        model_size: tamanho do modelo Whisper carregado pelo WhisperX.
        device: "cpu" ou "cuda". GPU é recomendada (o alinhamento CTC é pesado), não obrigatória.
        compute_type: repassado ao faster-whisper ("float16" em GPU, "int8" em CPU).
        language: idioma fixo, default "pt" (conteúdo PT-BR); também escolhe o modelo de alinhamento.
        batch_size: batch do transcribe em lote do WhisperX.
        diarize: liga a diarização real via pyannote. Requer `hf_token`.
        hf_token: token HuggingFace com os termos do pyannote aceitos. Sem ele, `diarize=True`
            apenas avisa e cai para o `diarizer` injetado (default `NullDiarizer`, speaker None).
        diarizer: diarizador do projeto aplicado ao final, quando a diarização do WhisperX não roda.
        model_factory: injeção do modelo ASR para teste; carregado uma única vez, no primeiro uso.
    """

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cpu",
        compute_type: str = "default",
        language: str | None = "pt",
        batch_size: int = 16,
        diarize: bool = False,
        hf_token: str | None = None,
        vocabulary: Vocabulary | None = None,
        normalization: NormalizationRules | None = NormalizationRules(),
        diarizer: Diarizer | None = None,
        model_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.batch_size = batch_size
        self.diarize = diarize
        self.hf_token = hf_token
        self.vocabulary = vocabulary or Vocabulary()
        self.normalization = normalization
        self.diarizer: Diarizer = diarizer or NullDiarizer()
        self._model_factory = model_factory or self._load_default_model
        self._model: Any | None = None
        self._align: tuple[str | None, Any, Any] | None = None

    @staticmethod
    def _whisperx() -> Any:
        import whisperx

        return whisperx

    def _asr_options(self) -> dict[str, Any]:
        """Mesmas travas anti-alucinacao e mesmo vocabulario do FasterWhisperTranscriber:
        o WhisperX roda faster-whisper por baixo, so recebe as opcoes no load do modelo
        em vez de na chamada de transcribe."""
        options: dict[str, Any] = {
            "condition_on_previous_text": False,
            "compression_ratio_threshold": 2.4,
            "no_speech_threshold": 0.6,
        }
        if self.vocabulary.initial_prompt:
            options["initial_prompt"] = self.vocabulary.initial_prompt
        if self.vocabulary.hotwords:
            options["hotwords"] = self.vocabulary.hotwords
        return supported_asr_options(options)

    def _load_default_model(self) -> Any:
        return self._whisperx().load_model(
            self.model_size,
            self.device,
            compute_type=self.compute_type,
            language=self.language,
            asr_options=self._asr_options(),
        )

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = self._model_factory()
        return self._model

    def _align_model(self, language: str | None) -> tuple[Any, Any]:
        if self._align is None or self._align[0] != language:
            model, metadata = self._whisperx().load_align_model(
                language_code=language, device=self.device
            )
            self._align = (language, model, metadata)
        return self._align[1], self._align[2]

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        """Roda as 4 etapas do WhisperX, logando inicio/fim/duracao de cada uma.

        Sem esse log, o processo inteiro fica em silencio por horas num video longo em
        CPU (nenhuma das 4 etapas do WhisperX reporta progresso por padrao) - o log aqui
        e o que diferencia "travado" de "lento mas trabalhando", que sem isso so da pra
        saber medindo uso de CPU do processo de fora.
        """
        whisperx = self._whisperx()
        overall_start = time.monotonic()

        logger.info("[1/4] carregando modelo ASR (%s, %s, %s)", self.model_size, self.device, self.compute_type)
        stage_start = time.monotonic()
        model = self.model
        logger.info("[1/4] modelo ASR carregado em %.1fs", time.monotonic() - stage_start)

        stage_start = time.monotonic()
        audio = whisperx.load_audio(str(audio_path))
        logger.info(
            "[2/4] audio carregado em %.1fs (%d amostras a 16kHz -> %.1f min)",
            time.monotonic() - stage_start,
            len(audio),
            len(audio) / 16_000 / 60,
        )

        stage_start = time.monotonic()
        raw = model.transcribe(audio, batch_size=self.batch_size)
        language = raw.get("language") or self.language
        logger.info(
            "[2/4] transcricao (ASR) concluida em %.1fs, %d segmento(s), idioma=%s",
            time.monotonic() - stage_start,
            len(raw.get("segments", [])),
            language,
        )

        stage_start = time.monotonic()
        align_model, metadata = self._align_model(language)
        aligned = whisperx.align(
            raw.get("segments", []),
            align_model,
            metadata,
            audio,
            self.device,
            return_char_alignments=False,
        )
        logger.info("[3/4] alinhamento CTC concluido em %.1fs", time.monotonic() - stage_start)

        diarized = False
        if self.diarize:
            if self.hf_token:
                stage_start = time.monotonic()
                pipeline = whisperx.diarize.DiarizationPipeline(
                    token=self.hf_token, device=self.device
                )
                aligned = whisperx.assign_word_speakers(pipeline(audio), aligned)
                diarized = True
                logger.info("[4/4] diarizacao concluida em %.1fs", time.monotonic() - stage_start)
            else:
                warnings.warn(
                    "WhisperXTranscriber: diarize=True sem hf_token; pyannote exige token "
                    "HuggingFace e aceite dos termos. Seguindo sem diarização real.",
                    RuntimeWarning,
                    stacklevel=2,
                )
        else:
            logger.info("[4/4] diarizacao desligada (diarize=False)")

        result = build_result_from_whisperx(
            aligned.get("segments", []),
            language=language,
            audio_path=audio_path,
            normalization=self.normalization,
        )
        if not diarized:
            result = self.diarizer.assign(result, audio_path)

        logger.info("WhisperX: pipeline completo em %.1fs", time.monotonic() - overall_start)
        return result
