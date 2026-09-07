"""Reaplica censor_text (versao corrigida) no titulo/descricao/thumbnail_headline dos
clips do rebrand (sem bloco de video original, sao arquivos locais, nao vem de YouTube).
Mesmo racional de apply_censor_to_output.py, mas sem original_video_url."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from clipador.export.writer import DEFAULT_SOCIAL_HANDLE, render_metadata_text, render_ready_to_post_text
from clipador.metadata.censor import censor_text
from clipador.metadata.models import ClipMetadata


def main() -> None:
    batch_root = Path(sys.argv[1])
    for clip_dir in sorted((batch_root / "short").iterdir()):
        metadata_json = clip_dir / "metadata.json"
        if not metadata_json.is_file():
            continue
        payload = json.loads(metadata_json.read_text(encoding="utf-8"))
        meta = payload.get("metadata")
        if not meta:
            continue

        before = (meta["title"], meta["description"], meta.get("thumbnail_headline") or "")
        meta["title"] = censor_text(meta["title"])
        meta["description"] = censor_text(meta["description"])
        meta["thumbnail_headline"] = censor_text(meta.get("thumbnail_headline") or "")
        after = (meta["title"], meta["description"], meta["thumbnail_headline"])
        changed = before != after

        metadata_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        clip_metadata = ClipMetadata(
            title=meta["title"],
            description=meta["description"],
            hashtags=meta.get("hashtags", []),
            format=meta.get("format", ""),
            kb_references=meta.get("kb_references", []),
            thumbnail_headline=meta["thumbnail_headline"],
        )
        (clip_dir / "metadata.txt").write_text(render_metadata_text(clip_metadata), encoding="utf-8")
        (clip_dir / "ready-to-post.txt").write_text(
            render_ready_to_post_text(
                clip_metadata.title, clip_metadata.description, clip_metadata.hashtags,
                handle=DEFAULT_SOCIAL_HANDLE, original_video_url=None,
            ),
            encoding="utf-8",
        )
        print(f"[{'censurado' if changed else 'sem alteracao'}] {clip_dir.name}")


if __name__ == "__main__":
    main()
