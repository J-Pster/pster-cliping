"""Recupera clips de rebrand cujo video final (with_outro.mp4) e thumbnail ja existem no
work_dir de staging (`.clipador/<batch>/<clip_id>/`), mas cujo `output/<batch>/short/<clip_id>/`
foi perdido (pasta output/ apagada). Nao reprocessa video nem thumbnail: so re-transcreve (local,
sem custo de nuvem) pra ter o excerto que alimenta a UNICA chamada de LLM que falta (metadados:
titulo/descricao/hashtags/headline), e escreve o pacote final via ExportWriter, exatamente como
`rebrand_batch` teria feito.

Le `videos_extraidos/metadata.json` (gerado por sessao anterior) pra saber, por video de origem,
qual clip_id/batch corresponde e se o rebrand daquele video foi concluido."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from clipador import category as category_module
from clipador.export.thumbnail_frame import ThumbnailFramePrepender  # noqa: F401 (garante import ok)
from clipador.export.writer import ExportWriter
from clipador.kb.knowledge import load_knowledge_base
from clipador.metadata.generator import generate_metadata
from clipador.pipeline import clip_excerpt
from clipador.rebrand.service import _build_candidate
from clipador.select.models import SHORT_FORMAT
from clipador.transcribe.whisper import FasterWhisperTranscriber

ENGINE_ROOT = Path(__file__).resolve().parent.parent
STAGE_ROOT = ENGINE_ROOT / ".clipador"
OUTPUT_ROOT = ENGINE_ROOT / "output"
CATEGORY = category_module.POLITICS_PERSON


def _clip_id_and_batch(rebrand_output_dir: str) -> tuple[str, str]:
    parts = Path(rebrand_output_dir).parts
    short_index = parts.index("short")
    return parts[-1], parts[short_index - 1]


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("uso: recover_rebrand_batch.py <pasta videos_extraidos>")

    input_dir = Path(sys.argv[1])
    metadata_path = input_dir / "metadata.json"
    tracker = json.loads(metadata_path.read_text(encoding="utf-8"))

    kb = load_knowledge_base(ENGINE_ROOT / "kb" / CATEGORY)
    transcriber = FasterWhisperTranscriber()
    writer = ExportWriter(OUTPUT_ROOT)

    recovered, skipped = [], []
    for entry in tracker["videos"]:
        if entry.get("rebrand_status") != "concluido":
            continue
        filename = entry["filename"]
        clip_id, batch_folder = _clip_id_and_batch(entry["rebrand_output_dir"])

        stage_dir = STAGE_ROOT / batch_folder / clip_id
        final_video = stage_dir / "with_outro.mp4"
        thumbnail_path = stage_dir / "thumbnail.png"
        source_video = input_dir / filename

        if not (final_video.is_file() and thumbnail_path.is_file() and source_video.is_file()):
            skipped.append((clip_id, "arquivo de origem/staging ausente"))
            print(f"[skip] {clip_id}: arquivo de origem/staging ausente")
            continue

        already_recovered = (OUTPUT_ROOT / batch_folder / "short" / clip_id / "video.mp4").is_file()
        if already_recovered:
            skipped.append((clip_id, "ja existe em output/"))
            print(f"[skip] {clip_id}: ja existe em output/")
            continue

        print(f"[transcrevendo] {clip_id} ({filename})")
        transcription = transcriber.transcribe(source_video)
        candidate = _build_candidate(transcription)
        excerpt = clip_excerpt(transcription, candidate.start_word_id, candidate.end_word_id)

        print(f"[metadados] {clip_id}")
        metadata = generate_metadata(candidate, excerpt, kb, category=CATEGORY)

        output = writer.write(
            batch_folder,
            clip_id,
            SHORT_FORMAT,
            final_video,
            metadata,
            None,
            thumbnail_path,
            candidate,
            batch_folder,
        )
        recovered.append(clip_id)
        print(f"[done] {clip_id} -> {output.directory}")

    print(f"\n{len(recovered)} recuperado(s), {len(skipped)} pulado(s).")


if __name__ == "__main__":
    main()
