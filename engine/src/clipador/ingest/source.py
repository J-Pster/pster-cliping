"""Adaptador de entrada: normaliza URL do YouTube ou arquivo local."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
_SHORT_HOSTS = {"youtu.be", "www.youtu.be"}
_PATH_PREFIXES = ("live", "shorts", "embed", "v")


class SourceKind(str, Enum):
    YOUTUBE_URL = "youtube_url"
    LOCAL_FILE = "local_file"


class IngestError(ValueError):
    """Entrada nao reconhecida como URL do YouTube nem como arquivo existente."""


@dataclass(frozen=True)
class IngestSource:
    kind: SourceKind
    value: str
    video_id: str | None = None

    @property
    def needs_download(self) -> bool:
        return self.kind is SourceKind.YOUTUBE_URL

    @property
    def path(self) -> Path | None:
        return Path(self.value) if self.kind is SourceKind.LOCAL_FILE else None


def extract_video_id(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return None

    host = parsed.netloc.lower()
    parts = [p for p in parsed.path.split("/") if p]

    if host in _SHORT_HOSTS:
        candidate = parts[0] if parts else ""
    elif host in _YOUTUBE_HOSTS:
        if parts and parts[0] == "watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) >= 2 and parts[0] in _PATH_PREFIXES:
            candidate = parts[1]
        else:
            candidate = ""
    else:
        return None

    return candidate if _VIDEO_ID_RE.match(candidate) else None


def is_youtube_url(url: str) -> bool:
    return extract_video_id(url) is not None


def resolve_source(entry: str | Path) -> IngestSource:
    """Roteia a entrada: URL do YouTube vai pro downloader, arquivo local vai direto pra transcricao."""
    raw = str(entry).strip()
    if not raw:
        raise IngestError("Entrada vazia")

    video_id = extract_video_id(raw)
    if video_id:
        return IngestSource(SourceKind.YOUTUBE_URL, raw, video_id)

    path = Path(raw).expanduser()
    if path.is_file():
        return IngestSource(SourceKind.LOCAL_FILE, str(path.resolve()))

    if path.exists():
        raise IngestError(f"Caminho existe mas nao e um arquivo: {raw}")

    raise IngestError(f"Entrada nao e uma URL de video do YouTube nem um arquivo existente: {raw}")
