"""Download de video via yt-dlp, isolado atras de uma interface trocavel."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from clipador.ingest.source import extract_video_id

logger = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class Chapter:
    title: str
    start: float
    end: float | None = None

    @property
    def duration(self) -> float | None:
        return None if self.end is None else self.end - self.start


@dataclass(frozen=True)
class DownloadResult:
    video_path: Path
    info: Mapping[str, Any] = field(default_factory=dict)
    info_json_path: Path | None = None
    chapters: tuple[Chapter, ...] = ()

    @property
    def video_id(self) -> str | None:
        return self.info.get("id")

    @property
    def duration(self) -> float | None:
        raw = self.info.get("duration")
        return None if raw is None else float(raw)


class Downloader(Protocol):
    def download(self, url: str) -> DownloadResult: ...


def extract_chapters(info: Mapping[str, Any] | None) -> tuple[Chapter, ...]:
    """Le os capitulos do info.json do yt-dlp como heuristica inicial de possiveis cortes."""
    if not info:
        return ()

    chapters: list[Chapter] = []
    for raw in info.get("chapters") or []:
        if not isinstance(raw, Mapping):
            continue
        start = raw.get("start_time")
        if start is None:
            continue
        end = raw.get("end_time")
        chapters.append(
            Chapter(
                title=str(raw.get("title") or "").strip(),
                start=float(start),
                end=None if end is None else float(end),
            )
        )
    return tuple(sorted(chapters, key=lambda c: c.start))


def load_info_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _default_ydl_factory(opts: dict[str, Any]) -> Any:
    import yt_dlp

    return yt_dlp.YoutubeDL(opts)


class YtDlpDownloader:
    """Baixa video+audio em qualidade alta e deixa o yt-dlp fazer o merge via ffmpeg.

    `cookies_from_browser` existe porque o YouTube bloqueia com frequencia (403) requisicoes
    de formato adaptativo (video+audio separados) vindas sem sessao autenticada - e o risco
    de anti-bot ja documentado no plano. Passar o nome de um navegador local logado
    (`"firefox"`, `"chrome"`, `"edge"`, ...) resolve isso lendo os cookies de sessao direto do
    perfil do navegador, sem exigir exportar nada manualmente. No Windows, `chrome`/`edge`
    costumam falhar com erro de DPAPI (chave de criptografia amarrada ao processo do
    navegador); `firefox` nao usa DPAPI e tende a funcionar de primeira.
    """

    def __init__(
        self,
        output_dir: str | Path,
        merge_output_format: str = "mp4",
        format_selector: str = "bestvideo*+bestaudio/best",
        write_info_json: bool = True,
        cookies_from_browser: str | None = None,
        extra_opts: Mapping[str, Any] | None = None,
        ydl_factory: Callable[[dict[str, Any]], Any] = _default_ydl_factory,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.merge_output_format = merge_output_format
        self.format_selector = format_selector
        self.write_info_json = write_info_json
        self.cookies_from_browser = cookies_from_browser
        self.extra_opts = dict(extra_opts or {})
        self._ydl_factory = ydl_factory

    def build_options(self) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "format": self.format_selector,
            "merge_output_format": self.merge_output_format,
            "writeinfojson": self.write_info_json,
            "outtmpl": str(self.output_dir / "%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }
        if self.cookies_from_browser:
            opts["cookiesfrombrowser"] = (self.cookies_from_browser,)
        opts.update(self.extra_opts)
        return opts

    def download(self, url: str) -> DownloadResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        cached = self._cached_result(url)
        if cached is not None:
            logger.info(
                "Reaproveitando download em cache sem falar com a rede: %s", cached.video_path
            )
            return cached

        ydl = self._ydl_factory(self.build_options())

        info = ydl.extract_info(url, download=True)
        if not info:
            raise DownloadError(f"yt-dlp nao retornou metadados para {url}")

        video_path = Path(self._resolve_filepath(ydl, info))
        info_json_path = video_path.with_suffix(".info.json") if self.write_info_json else None
        if info_json_path is not None and not info_json_path.exists():
            info_json_path = None

        return DownloadResult(
            video_path=video_path,
            info=info,
            info_json_path=info_json_path,
            chapters=extract_chapters(info),
        )

    def _cached_result(self, url: str) -> DownloadResult | None:
        """Reaproveita um download anterior sem chamar `extract_info`: mesmo com o
        `.mp4` ja em `output_dir`, o yt-dlp precisa resolver formatos no YouTube pra
        cada re-execucao, e isso falha com "Sign in to confirm you're not a bot" depois
        de alguns acessos ao mesmo video (ver P2.2). So reaproveita quando da pra extrair
        o video_id da URL SEM rede (`extract_video_id`, o mesmo parser da ingestao) e o
        `.info.json` (escrito por um download anterior) ainda existe ao lado do arquivo -
        os dois sao a evidencia local de que ja foi baixado, nunca inferido de outra
        forma."""
        video_id = extract_video_id(url)
        if video_id is None:
            return None

        video_path = self.output_dir / f"{video_id}.{self.merge_output_format}"
        info_json_path = video_path.with_suffix(".info.json")
        if not video_path.is_file() or not info_json_path.is_file():
            return None

        info = load_info_json(info_json_path)
        return DownloadResult(
            video_path=video_path,
            info=info,
            info_json_path=info_json_path,
            chapters=extract_chapters(info),
        )

    @staticmethod
    def _resolve_filepath(ydl: Any, info: Mapping[str, Any]) -> str:
        requested = info.get("requested_downloads") or []
        if requested:
            filepath = requested[0].get("filepath")
            if filepath:
                return filepath

        filepath = info.get("filepath") or info.get("_filename")
        if filepath:
            return filepath

        prepare = getattr(ydl, "prepare_filename", None)
        if prepare is not None:
            return prepare(info)

        raise DownloadError("Nao foi possivel determinar o caminho do arquivo baixado")
