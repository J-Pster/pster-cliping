"""Transcricao via API (AssemblyAI): alternativa em nuvem ao Whisper/WhisperX local.

Existe porque processamento 100% local (WhisperX medium + alinhamento CTC + diarizacao
pyannote) em CPU pode levar horas num video de dezenas de minutos, mesmo em hardware forte -
e um trade-off real de tempo, nao um bug a se corrigir. AssemblyAI devolve timestamp por
palavra e diarizacao embutidos numa chamada so, tipicamente em minutos (nao horas) pra um
video de 40-60min, ao custo de $ por minuto de audio e de mandar o audio pra fora.

API: `pip install assemblyai` (nao esta em `[project.optional-dependencies]` por padrao -
adicione se for usar esta opcao). Requer `ASSEMBLYAI_API_KEY` (console.assemblyai.com).

Mesma trade-off de qualidade ja documentada no ledger: diarizacao em nuvem perde mais fala em
crosstalk que o pyannote local (~20-25% vs ~8% em benchmarks), o cenario mais comum em
debate/entrevista politica. Use esta opcao quando o tempo de processamento importa mais que
esse ganho de precisao (ex: primeiro teste rapido, video longo, prazo apertado) - a escolha e
por chamador, nao automatica: nada aqui troca o default do projeto (`FasterWhisperTranscriber`)
nem desaconselha o `WhisperXTranscriber` local para produção.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from clipador.transcribe.models import Segment, TranscriptionResult, Word, renumber_words
from clipador.transcribe.normalize import NormalizationRules, normalize_transcription
from clipador.transcribe.vocabulary import Vocabulary

logger = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    pass


def _ms_to_s(value: Any, fallback: float = 0.0) -> float:
    return fallback if value is None else float(value) / 1000.0


def build_result_from_assemblyai(
    transcript: Any,
    audio_path: str | Path | None = None,
    normalization: NormalizationRules | None = NormalizationRules(),
) -> TranscriptionResult:
    """Converte a resposta do SDK da AssemblyAI no schema estavel do projeto.

    A API devolve uma lista PLANA de palavras (`transcript.words`), sem segmentacao por
    frase pronta - agrupamos por `utterances` quando a diarizacao estiver ligada (cada
    utterance ja e um turno de fala de 1 speaker), ou por frases via `transcript.text`
    quando nao. Aqui optamos pelo caminho mais simples e robusto: 1 segmento por
    utterance (ou 1 segmento unico sem diarizacao), com as palavras de cada um.
    """
    words_by_speaker: list[tuple[str | None, list[Any]]] = []
    utterances = getattr(transcript, "utterances", None)
    if utterances:
        for utterance in utterances:
            words_by_speaker.append((getattr(utterance, "speaker", None), utterance.words or []))
    else:
        words_by_speaker.append((None, transcript.words or []))

    segments: list[Segment] = []
    for speaker, raw_words in words_by_speaker:
        words: list[Word] = []
        for raw_word in raw_words:
            start = _ms_to_s(getattr(raw_word, "start", None))
            end = _ms_to_s(getattr(raw_word, "end", None), fallback=start)
            words.append(
                Word(
                    id=0,
                    text=str(getattr(raw_word, "text", "")).strip(),
                    start=start,
                    end=end,
                    speaker=speaker,
                )
            )
        if not words:
            continue
        segments.append(
            Segment(
                id=0,
                start=words[0].start,
                end=words[-1].end,
                text=" ".join(w.text for w in words),
                words=words,
                speaker=speaker,
            )
        )

    renumber_words(segments)
    result = TranscriptionResult(
        segments=segments,
        language=getattr(transcript, "language_code", None),
        duration=max((s.end for s in segments), default=None),
        audio_path=None if audio_path is None else str(audio_path),
    )
    return result if normalization is None else normalize_transcription(result, normalization)


class AssemblyAITranscriber:
    """Transcriber via API da AssemblyAI. Mesmo contrato: `transcribe(audio_path) -> TranscriptionResult`.

    Args:
        api_key: chave da AssemblyAI (console.assemblyai.com). Obrigatoria a menos que
            `client_factory` seja passado (uso em teste).
        language_code: idioma do audio, default "pt" (PT-BR).
        diarize: liga `speaker_labels` na API (diarizacao em nuvem).
        client_factory: injecao do client pra teste - se `None`, importa e autentica o SDK
            oficial (`assemblyai`) so na primeira transcricao (import lazy).
    """

    def __init__(
        self,
        api_key: str | None = None,
        language_code: str | None = "pt",
        diarize: bool = True,
        vocabulary: Vocabulary | None = None,
        normalization: NormalizationRules | None = NormalizationRules(),
        client_factory: Callable[[], Any] | None = None,
        config_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.language_code = language_code
        self.diarize = diarize
        self.vocabulary = vocabulary or Vocabulary()
        self.normalization = normalization
        self._client_factory = client_factory
        self._config_factory = config_factory
        self._client: Any | None = None

    def _load_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client

        import assemblyai as aai

        if not self.api_key:
            raise TranscriptionError(
                "ASSEMBLYAI_API_KEY nao configurada (obtenha em console.assemblyai.com)"
            )
        aai.settings.api_key = self.api_key
        self._client = aai.Transcriber()
        return self._client

    def _build_config(self) -> Any:
        if self._config_factory is not None:
            return self._config_factory()
        if self._client_factory is not None:
            # Client injetado (teste) sem config_factory proprio: o fake client nao
            # inspeciona o config, entao um objeto simples basta.
            return {
                "language_code": self.language_code,
                "speaker_labels": self.diarize,
                "word_boost": list(self.vocabulary.terms),
            }

        import assemblyai as aai

        # `word_boost` e o equivalente do `hotwords`/`initial_prompt` do Whisper na API da
        # AssemblyAI: enviesa o reconhecimento pros termos de dominio da KB.
        return aai.TranscriptionConfig(
            language_code=self.language_code,
            speaker_labels=self.diarize,
            word_boost=list(self.vocabulary.terms),
        )

    def transcribe(self, audio_path: str | Path) -> TranscriptionResult:
        client = self._load_client()
        config = self._build_config()

        logger.info(
            "AssemblyAI: enviando %s pra transcricao em nuvem (diarizacao=%s)",
            audio_path,
            self.diarize,
        )
        stage_start = time.monotonic()
        transcript = client.transcribe(str(audio_path), config)
        elapsed = time.monotonic() - stage_start

        status = getattr(transcript, "status", None)
        error = getattr(transcript, "error", None)
        if status == "error" or error:
            raise TranscriptionError(f"AssemblyAI retornou erro: {error or status}")

        logger.info("AssemblyAI: transcricao concluida em %.1fs", elapsed)
        return build_result_from_assemblyai(
            transcript, audio_path=audio_path, normalization=self.normalization
        )
