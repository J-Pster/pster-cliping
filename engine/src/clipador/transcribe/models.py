"""Modelo e serializacao da transcricao (timestamp por palavra + speaker)."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# 2: a transcricao passou a ser NORMALIZADA antes de ser salva (sigla remontada,
# pontuacao orfa colada, duracao minima por palavra, repeticao alucinada cortada - ver
# `clipador.transcribe.normalize`). A normalizacao renumera os `word_id`, entao um cache
# de schema 1 nao e compativel com nada que guarde word_id: `load_cached_transcription`
# trata cache antigo como ausente e o pipeline retranscreve.
SCHEMA_VERSION = 2


@dataclass
class Word:
    id: int
    text: str
    start: float
    end: float
    speaker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "speaker": self.speaker,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Word:
        return cls(
            id=int(data["id"]),
            text=data["text"],
            start=float(data["start"]),
            end=float(data["end"]),
            speaker=data.get("speaker"),
        )


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    speaker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "speaker": self.speaker,
            "words": [w.to_dict() for w in self.words],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Segment:
        return cls(
            id=int(data["id"]),
            start=float(data["start"]),
            end=float(data["end"]),
            text=data["text"],
            words=[Word.from_dict(w) for w in data.get("words", [])],
            speaker=data.get("speaker"),
        )


@dataclass
class TranscriptionResult:
    segments: list[Segment] = field(default_factory=list)
    language: str | None = None
    duration: float | None = None
    audio_path: str | None = None

    @property
    def words(self) -> list[Word]:
        return [w for segment in self.segments for w in segment.words]

    def word_by_id(self, word_id: int) -> Word:
        for word in self.words:
            if word.id == word_id:
                return word
        raise KeyError(f"word_id inexistente na transcricao: {word_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "language": self.language,
            "duration": self.duration,
            "audio_path": self.audio_path,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TranscriptionResult:
        version = data.get("version")
        if version != SCHEMA_VERSION:
            raise ValueError(f"Versao de schema de transcricao nao suportada: {version}")
        return cls(
            segments=[Segment.from_dict(s) for s in data.get("segments", [])],
            language=data.get("language"),
            duration=data.get("duration"),
            audio_path=data.get("audio_path"),
        )


class Transcriber(Protocol):
    def transcribe(self, audio_path: str | Path) -> TranscriptionResult: ...


def renumber_words(segments: Sequence[Segment]) -> None:
    """Garante ids sequenciais e globais de palavra, referencia estavel para a selecao por LLM."""
    next_id = 0
    for segment_index, segment in enumerate(segments):
        segment.id = segment_index
        for word in segment.words:
            word.id = next_id
            next_id += 1


def save_transcription(result: TranscriptionResult, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def load_transcription(path: str | Path) -> TranscriptionResult:
    return TranscriptionResult.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def load_cached_transcription(path: str | Path) -> TranscriptionResult | None:
    """Transcricao do cache, ou `None` quando o arquivo nao existe ou e de um schema
    antigo. Cache invalido nao e erro: e so trabalho a refazer, e derrubar o pipeline por
    causa dele obrigaria o usuario a apagar arquivo na mao depois de todo upgrade."""
    target = Path(path)
    if not target.is_file():
        return None
    try:
        return load_transcription(target)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        logger.info("Cache de transcricao descartado (%s): %s", target, exc)
        return None
