"""Regera o ready-to-post.txt de todos os clips (short e long) de uma pasta de video ja
exportada, usando o metadata.json existente de cada clip. Usado quando render_ready_to_post_text
ganha um campo novo (ex.: bloco de video original) e os clips ja exportados precisam ser
atualizados sem reprocessar o pipeline inteiro."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from clipador.export.writer import DEFAULT_SOCIAL_HANDLE, render_ready_to_post_text


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("uso: regen_ready_to_post.py <pasta do video> <url original>")

    video_dir = Path(sys.argv[1])
    original_video_url = sys.argv[2]

    for subdir in ("short", "long"):
        base = video_dir / subdir
        if not base.is_dir():
            continue
        for clip_dir in sorted(base.iterdir()):
            metadata_json = clip_dir / "metadata.json"
            if not metadata_json.is_file():
                continue
            payload = json.loads(metadata_json.read_text(encoding="utf-8"))
            meta = payload.get("metadata")
            if not meta:
                print(f"[skip] {clip_dir.name} (sem metadata)")
                continue

            text = render_ready_to_post_text(
                meta["title"],
                meta["description"],
                meta["hashtags"],
                handle=DEFAULT_SOCIAL_HANDLE,
                original_video_url=original_video_url,
            )
            (clip_dir / "ready-to-post.txt").write_text(text, encoding="utf-8")
            print(f"[done] {clip_dir.name}")


if __name__ == "__main__":
    main()
