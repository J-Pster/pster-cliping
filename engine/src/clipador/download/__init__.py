"""Etapa 2: download de vídeo (yt-dlp) e metadados (YouTube Data API v3)."""

from clipador.download.downloader import (
    Chapter,
    DownloadError,
    Downloader,
    DownloadResult,
    YtDlpDownloader,
    extract_chapters,
    load_info_json,
)
from clipador.download.metadata import (
    MetadataError,
    VideoMetadata,
    YouTubeMetadataFetcher,
    parse_video_item,
    pick_thumbnail,
)

__all__ = [
    "Chapter",
    "DownloadError",
    "DownloadResult",
    "Downloader",
    "MetadataError",
    "VideoMetadata",
    "YouTubeMetadataFetcher",
    "YtDlpDownloader",
    "extract_chapters",
    "load_info_json",
    "parse_video_item",
    "pick_thumbnail",
]
