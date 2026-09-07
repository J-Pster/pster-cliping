"""Metadados oficiais via YouTube Data API v3."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

_THUMBNAIL_PREFERENCE = ("maxres", "standard", "high", "medium", "default")


class MetadataError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoMetadata:
    video_id: str
    title: str = ""
    description: str = ""
    tags: tuple[str, ...] = ()
    channel_title: str = ""
    published_at: str = ""
    duration: str = ""
    thumbnail_url: str | None = None
    license: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)


def _default_client_factory() -> Any:
    from clipador.youtube.client import get_client

    return get_client()


def pick_thumbnail(thumbnails: Mapping[str, Any] | None) -> str | None:
    if not thumbnails:
        return None
    for key in _THUMBNAIL_PREFERENCE:
        entry = thumbnails.get(key)
        if isinstance(entry, Mapping) and entry.get("url"):
            return entry["url"]
    return None


def parse_video_item(item: Mapping[str, Any]) -> VideoMetadata:
    snippet = item.get("snippet") or {}
    content = item.get("contentDetails") or {}
    status = item.get("status") or {}
    return VideoMetadata(
        video_id=str(item.get("id") or ""),
        title=snippet.get("title") or "",
        description=snippet.get("description") or "",
        tags=tuple(snippet.get("tags") or ()),
        channel_title=snippet.get("channelTitle") or "",
        published_at=snippet.get("publishedAt") or "",
        duration=content.get("duration") or "",
        thumbnail_url=pick_thumbnail(snippet.get("thumbnails")),
        license=status.get("license") or "",
        raw=item,
    )


class YouTubeMetadataFetcher:
    """Busca descricao, tags, thumbnail em alta e duracao oficiais de um video."""

    PARTS = "snippet,contentDetails,status"

    def __init__(self, client_factory: Callable[[], Any] = _default_client_factory) -> None:
        self._client_factory = client_factory
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def fetch(self, video_id: str) -> VideoMetadata:
        response = self.client.videos().list(part=self.PARTS, id=video_id).execute()
        items = (response or {}).get("items") or []
        if not items:
            raise MetadataError(f"Nenhum video encontrado na Data API para o id {video_id}")
        return parse_video_item(items[0])
