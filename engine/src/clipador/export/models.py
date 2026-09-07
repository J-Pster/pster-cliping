"""Pacote final de um clipe: onde cada artefato foi parar e em que ponto da revisao ele esta."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clipador.metadata.models import ClipMetadata

REVIEW_PENDING = "review_pending"
REVIEW_APPROVED = "review_approved"


class ExportError(RuntimeError):
    pass


@dataclass
class ClipOutput:
    """Artefatos ja organizados de UM clipe, prontos para a revisao editorial (etapa [9])."""

    clip_id: str
    video_id: str
    format: str
    directory: Path
    video_path: Path
    subtitles_path: Path | None = None
    thumbnail_path: Path | None = None
    metadata_path: Path | None = None
    metadata: ClipMetadata | None = None
    review_status: str = REVIEW_PENDING
    review_marker_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def kb_references(self) -> list[str]:
        return list(self.metadata.kb_references) if self.metadata else []

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "video_id": self.video_id,
            "format": self.format,
            "directory": str(self.directory),
            "video_path": str(self.video_path),
            "subtitles_path": None if self.subtitles_path is None else str(self.subtitles_path),
            "thumbnail_path": None if self.thumbnail_path is None else str(self.thumbnail_path),
            "metadata_path": None if self.metadata_path is None else str(self.metadata_path),
            "metadata": None if self.metadata is None else self.metadata.to_dict(),
            "review_status": self.review_status,
            **self.extra,
        }
