"""CLI de postagem: `clipador-publish buffer-channels` e `clipador-publish publish <clip-dir>`.

Comando separado do `clipador` principal (pipeline de geracao) de proposito:
sao ciclos de vida diferentes, um roda uma vez por video, o outro roda uma vez
por publicacao, e misturar os dois no mesmo parser so complicaria os testes e
o help de ambos sem ganhar nada.

Publicacao vai toda via Buffer (https://buffer.com): nao ha mais login por
plataforma, so uma API key global do Buffer (`BUFFER_API_KEY` no .env) e um
canal do Buffer configurado por grupo (conta conectada) + plataforma
(`BUFFER_CHANNEL_<GRUPO>_<PLATAFORMA>`). O grupo e escolhido em toda
publicacao via `--group`.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from clipador.export.review import MARKER_NAME
from clipador.export.writer import METADATA_JSON_NAME
from clipador.publish import buffer_publisher
from clipador.publish.models import ALL_GROUPS, ALL_PLATFORMS, LONG_FORMAT_PLATFORMS, PublishResult
from clipador.select.models import LONG_FORMAT

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipador-publish",
        description="Publica clipes ja aprovados em YouTube, Instagram e TikTok via Buffer.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "buffer-channels", help="Lista os canais conectados na conta Buffer (pra descobrir os IDs)"
    )

    publish_parser = subparsers.add_parser("publish", help="Publica um clipe ja aprovado")
    publish_parser.add_argument("clip_dir", type=Path, help="Diretorio do clipe exportado")
    publish_parser.add_argument(
        "--platforms",
        default=",".join(ALL_PLATFORMS),
        help=f"Lista separada por virgula, dentre {ALL_PLATFORMS}",
    )
    publish_parser.add_argument(
        "--group",
        choices=ALL_GROUPS,
        required=True,
        help=(
            "Conta Buffer conectada pra onde publicar (grupo de canais): "
            f"{ALL_GROUPS}"
        ),
    )
    publish_parser.add_argument("--verbose", action="store_true")

    return parser


def _run_buffer_channels() -> int:
    channels = buffer_publisher.list_channels()
    if not channels:
        print("Nenhum canal encontrado na conta Buffer.")
        return 0
    for channel in channels:
        print(f"{channel['id']}  {channel['name']}  ({channel['service']})")
    return 0


def _load_clip(clip_dir: Path) -> dict:
    if (clip_dir / MARKER_NAME).is_file():
        raise SystemExit(
            f"Clipe em {clip_dir} ainda esta pendente de revisao ({MARKER_NAME}), "
            "aprove antes de publicar."
        )
    metadata_path = clip_dir / METADATA_JSON_NAME
    if not metadata_path.is_file():
        raise SystemExit(f"{metadata_path} nao encontrado")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    video_matches = sorted(clip_dir.glob("video.*"))
    if not video_matches:
        raise SystemExit(f"Nenhum arquivo de video encontrado em {clip_dir}")
    metadata["_video_path"] = video_matches[0]
    return metadata


def _publish_one(platform: str, clip: dict, group: str) -> PublishResult:
    title = clip.get("title", "")
    description = clip.get("description", "")
    hashtags = clip.get("hashtags", [])
    video_path: Path = clip["_video_path"]

    try:
        return buffer_publisher.publish(video_path, title, description, hashtags, platform, group)
    except Exception as exc:  # plataformas sao independentes: uma falhar nao trava as outras
        return PublishResult(platform, False, message=str(exc))


def _run_publish(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    unknown = set(platforms) - set(ALL_PLATFORMS)
    if unknown:
        raise SystemExit(f"Plataforma(s) desconhecida(s): {sorted(unknown)}")

    clip = _load_clip(args.clip_dir)
    clip_format = clip.get("format", "")

    results: list[PublishResult] = []
    for platform in platforms:
        if clip_format == LONG_FORMAT and platform not in LONG_FORMAT_PLATFORMS:
            results.append(
                PublishResult(platform, False, message="clipe longo (16:9) so vai pro YouTube")
            )
            continue
        results.append(_publish_one(platform, clip, args.group))

    failures = 0
    for result in results:
        status = "OK" if result.success else "FALHOU"
        detail = result.remote_url or result.remote_id or result.message
        print(f"{result.platform}: {status} {detail}")
        if not result.success:
            failures += 1

    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "buffer-channels":
        return _run_buffer_channels()
    return _run_publish(args)


if __name__ == "__main__":
    raise SystemExit(main())
