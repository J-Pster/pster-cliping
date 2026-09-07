"""Repara clips do short/ cujo video.mp4 nao teve a thumbnail.png prendida nos 3
primeiros frames (so 02 e 06 saíram certos numa run anterior). Reusa o mesmo
ThumbnailFramePrepender do pipeline (mesmo comando ffmpeg, mesmo default de codec)
para que o resultado seja identico ao que o pipeline normal produziria."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from clipador.export.thumbnail_frame import ThumbnailFramePrepender

SHORT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else None
SKIP_DIRS = {"90_clip_02_short_9x16", "88_clip_06_short_9x16"}


def main() -> None:
    if SHORT_DIR is None:
        raise SystemExit("uso: fix_thumbnail_frames.py <pasta short>")

    prepender = ThumbnailFramePrepender()

    clip_dirs = sorted(p for p in SHORT_DIR.iterdir() if p.is_dir())
    for clip_dir in clip_dirs:
        if clip_dir.name in SKIP_DIRS:
            print(f"[skip] {clip_dir.name} (ja atualizado)")
            continue

        video_path = clip_dir / "video.mp4"
        thumbnail_path = clip_dir / "thumbnail.png"
        if not video_path.is_file() or not thumbnail_path.is_file():
            print(f"[skip] {clip_dir.name} (video.mp4 ou thumbnail.png ausente)")
            continue

        with tempfile.TemporaryDirectory(dir=clip_dir) as tmp_dir:
            tmp_output = Path(tmp_dir) / "video_with_thumb.mp4"
            print(f"[run]  {clip_dir.name}")
            prepender.prepend(video_path, thumbnail_path, tmp_output)
            tmp_output.replace(video_path)
        print(f"[done] {clip_dir.name}")


if __name__ == "__main__":
    main()
