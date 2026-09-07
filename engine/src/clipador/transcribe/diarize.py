"""Diarizacao: interface + adapter que combina segments da transcricao com turnos de fala.

O default e o NullDiarizer (todo speaker fica None). A integracao real com pyannote
entra depois plugando um Diarizer que produza SpeakerTurn e reuse apply_speaker_turns.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from clipador.transcribe.models import TranscriptionResult


@dataclass(frozen=True)
class SpeakerTurn:
    speaker: str
    start: float
    end: float


class Diarizer(Protocol):
    def assign(self, result: TranscriptionResult, audio_path: str | Path) -> TranscriptionResult: ...


class NullDiarizer:
    """Nao atribui speaker, mantem a estrutura pronta para a diarizacao real."""

    def assign(self, result: TranscriptionResult, audio_path: str | Path) -> TranscriptionResult:
        return result


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def speaker_at(turns: Sequence[SpeakerTurn], start: float, end: float) -> str | None:
    """Speaker com maior sobreposicao temporal com o intervalo dado."""
    best: str | None = None
    best_overlap = 0.0
    for turn in turns:
        value = _overlap(start, end, turn.start, turn.end)
        if value > best_overlap:
            best_overlap = value
            best = turn.speaker
    return best


def apply_speaker_turns(
    result: TranscriptionResult, turns: Sequence[SpeakerTurn]
) -> TranscriptionResult:
    """Combina palavras/segments com turnos de fala, atribuindo o speaker dominante."""
    for segment in result.segments:
        for word in segment.words:
            word.speaker = speaker_at(turns, word.start, word.end)

        speakers = [w.speaker for w in segment.words if w.speaker]
        segment.speaker = (
            max(set(speakers), key=speakers.count)
            if speakers
            else speaker_at(turns, segment.start, segment.end)
        )
    return result
