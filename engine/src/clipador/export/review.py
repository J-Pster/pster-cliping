"""Checkpoint de revisao editorial (etapa [9]): nada sai do pipeline ja dado como publicavel.

A revisao em si e humana e nao tem ferramenta. O que existe aqui e so o ponto de
parada: todo clipe exportado nasce marcado como pendente, e alguem precisa aprovar.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from clipador.export.models import REVIEW_APPROVED, REVIEW_PENDING, ClipOutput

MARKER_NAME = "REVIEW_PENDING"
MARKER_TEXT = (
    "Clipe aguardando revisao editorial humana.\n"
    "Confira se o corte nao descontextualiza a fala e se titulo/descricao batem com o "
    "que foi realmente dito.\n"
    "Apague este arquivo (ou use ReviewQueue.approve) para marcar como revisado.\n"
)


class ReviewQueue:
    """Marca clipes como pendentes de revisao e lista o que ainda nao foi aprovado."""

    def __init__(self, marker_name: str = MARKER_NAME) -> None:
        self.marker_name = marker_name

    def enqueue(self, clip: ClipOutput) -> ClipOutput:
        marker = clip.directory / self.marker_name
        marker.write_text(MARKER_TEXT, encoding="utf-8")
        clip.review_status = REVIEW_PENDING
        clip.review_marker_path = marker
        return clip

    def approve(self, clip: ClipOutput) -> ClipOutput:
        marker = clip.directory / self.marker_name
        marker.unlink(missing_ok=True)
        clip.review_status = REVIEW_APPROVED
        clip.review_marker_path = None
        return clip

    def is_pending(self, clip: ClipOutput) -> bool:
        return (clip.directory / self.marker_name).is_file()

    def pending(self, output_root: str | Path) -> Iterator[Path]:
        """Diretorios de clipe que ainda tem o marcador, varrendo a raiz de saida
        (`output_root/video_id/<short|long>/clip_id/`)."""
        for marker in sorted(Path(output_root).glob(f"*/*/*/{self.marker_name}")):
            yield marker.parent
