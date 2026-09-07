"""Etapa 1: adaptadores de entrada (URL do YouTube ou arquivo local)."""

from clipador.ingest.source import (
    IngestError,
    IngestSource,
    SourceKind,
    extract_video_id,
    is_youtube_url,
    resolve_source,
)

__all__ = [
    "IngestError",
    "IngestSource",
    "SourceKind",
    "extract_video_id",
    "is_youtube_url",
    "resolve_source",
]
