"""Combina nitidez + qualidade de rosto numa pontuacao final e escolhe o melhor candidato."""

from __future__ import annotations

from collections.abc import Sequence

from clipador.thumbnail.models import ScoredFrame, ThumbnailError


class ThumbnailCandidateRanker:
    """Funcao pura de ranking: soma ponderada dos scores individuais de cada candidato."""

    def __init__(self, sharpness_weight: float = 0.4, face_weight: float = 0.6) -> None:
        self.sharpness_weight = sharpness_weight
        self.face_weight = face_weight

    def combined_score(self, candidate: ScoredFrame) -> float:
        return (
            candidate.sharpness_score * self.sharpness_weight
            + candidate.face_score * self.face_weight
        )

    def rank(self, candidates: Sequence[ScoredFrame]) -> list[ScoredFrame]:
        return sorted(candidates, key=self.combined_score, reverse=True)

    def best(self, candidates: Sequence[ScoredFrame]) -> ScoredFrame:
        if not candidates:
            raise ThumbnailError("Nenhum candidato para ranquear")
        return self.rank(candidates)[0]
