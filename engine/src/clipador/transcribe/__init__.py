"""Etapa 3: transcrição com timestamp por palavra e diarização (WhisperX/faster-whisper/nuvem)."""

from clipador.transcribe.audio import extract_audio, needs_extraction
from clipador.transcribe.diarize import (
    Diarizer,
    NullDiarizer,
    SpeakerTurn,
    apply_speaker_turns,
    speaker_at,
)
from clipador.transcribe.elevenlabs_transcriber import (
    ElevenLabsTranscriber,
    build_result_from_elevenlabs,
)
from clipador.transcribe.factory import (
    BACKENDS,
    CLOUD_BACKENDS,
    DEFAULT_BACKEND,
    DEFAULT_MODEL_SIZE,
    TranscriberConfigError,
    TranscriberSettings,
    build_transcriber,
)
from clipador.transcribe.models import (
    SCHEMA_VERSION,
    Segment,
    Transcriber,
    TranscriptionResult,
    Word,
    load_cached_transcription,
    load_transcription,
    renumber_words,
    save_transcription,
)
from clipador.transcribe.normalize import (
    NormalizationRules,
    normalize_transcription,
    normalize_words,
)
from clipador.transcribe.vocabulary import Vocabulary, build_vocabulary, extract_terms
from clipador.transcribe.whisper import FasterWhisperTranscriber, build_result
from clipador.transcribe.whisperx_transcriber import (
    WhisperXTranscriber,
    build_result_from_whisperx,
)

__all__ = [
    "BACKENDS",
    "CLOUD_BACKENDS",
    "DEFAULT_BACKEND",
    "DEFAULT_MODEL_SIZE",
    "SCHEMA_VERSION",
    "Diarizer",
    "ElevenLabsTranscriber",
    "FasterWhisperTranscriber",
    "NormalizationRules",
    "NullDiarizer",
    "Segment",
    "SpeakerTurn",
    "Transcriber",
    "TranscriberConfigError",
    "TranscriberSettings",
    "TranscriptionResult",
    "Vocabulary",
    "WhisperXTranscriber",
    "Word",
    "apply_speaker_turns",
    "build_result",
    "build_result_from_elevenlabs",
    "build_result_from_whisperx",
    "build_transcriber",
    "build_vocabulary",
    "extract_audio",
    "extract_terms",
    "load_cached_transcription",
    "load_transcription",
    "needs_extraction",
    "normalize_transcription",
    "normalize_words",
    "renumber_words",
    "save_transcription",
    "speaker_at",
]
