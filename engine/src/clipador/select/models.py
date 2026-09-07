"""Estrutura de um candidato a clipe apontado pelo LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SHORT_FORMAT = "short_9x16"
LONG_FORMAT = "long_16x9"
CLIP_FORMATS = (SHORT_FORMAT, LONG_FORMAT)

MIN_SCORE = 0
MAX_SCORE = 99

# Janela de duracao alvo por formato: curto e uma peca autonoma pra feed/Reels/Shorts,
# longo e um "melhores momentos" editado pra YouTube. Ver DURATION_BOUNDS_SECONDS em
# select/selector.py para a tolerancia aplicada em cima destes limites.
# Esteve em 20-40s (alvo 30s) por um periodo curto - revertido a pedido do usuario
# (2026-09-04): clipe de 30s saia descontextualizado. Nao mexer sem pedido explicito de novo.
SHORT_MIN_SECONDS = 60.0
SHORT_MAX_SECONDS = 90.0
# Alvo pedido pelo usuario: 10min, "2 pra menos, 2 pra mais" (pesquisa de sweet spot de
# retencao/algoritmo do YouTube apontou 8-12min como faixa forte pra conteudo de
# comentario/analise politica). Era 300-900s (5-15min) antes desta mudanca.
LONG_MIN_SECONDS = 480.0
LONG_MAX_SECONDS = 720.0


@dataclass
class ClipCandidate:
    start_word_id: int
    end_word_id: int
    format: str
    score: int
    justificativa: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_word_id": self.start_word_id,
            "end_word_id": self.end_word_id,
            "format": self.format,
            "score": self.score,
            "justificativa": self.justificativa,
            "start": self.start,
            "end": self.end,
        }
