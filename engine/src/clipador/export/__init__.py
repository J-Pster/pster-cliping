"""Etapa 10: exportação dos arquivos finais (vídeo, legenda, metadados, thumbnail)."""

from clipador.export.cutter import ClipCutter
from clipador.export.models import (
    REVIEW_APPROVED,
    REVIEW_PENDING,
    ClipOutput,
    ExportError,
)
from clipador.export.review import MARKER_NAME, ReviewQueue
from clipador.export.watermark import WatermarkError, WatermarkImages, WatermarkOverlay
from clipador.export.writer import ExportWriter, render_metadata_text

__all__ = [
    "REVIEW_APPROVED",
    "REVIEW_PENDING",
    "MARKER_NAME",
    "ClipCutter",
    "ClipOutput",
    "ExportError",
    "ExportWriter",
    "ReviewQueue",
    "WatermarkError",
    "WatermarkImages",
    "WatermarkOverlay",
    "render_metadata_text",
]
