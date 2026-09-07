"""Tipos base da geracao de thumbnail: erro e candidato pontuado."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ThumbnailError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScoredFrame:
    """Um frame candidato a thumbnail com seus scores individuais ja calculados."""

    frame: Any
    sharpness_score: float
    face_score: float
