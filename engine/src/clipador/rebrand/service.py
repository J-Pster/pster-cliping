"""Rebranding em LOTE de videos curtos ja existentes, fora do pipeline principal.

Cada video de uma pasta de entrada vira um "clipe" dentro de UMA pasta de saida em
`output/` (a mesma raiz do pipeline principal), na mesma estrutura ja usada por
`clipador.export.writer.ExportWriter`
(`output/<batch_folder>/short/<clip_id>/{video.mp4, thumbnail.png, metadata.json,
metadata.txt, ready-to-post.txt, REVIEW_PENDING}`).

Reaproveita 100% do stack ja existente do pipeline principal em vez de reimplementar:
transcricao (`FasterWhisperTranscriber`), geracao de metadata via LLM
(`generate_metadata`, mesmo dossie/knowledge base), composicao de thumbnail (mesmo
padrao de `clipador.pipeline._default_thumbnail_builder`), gravacao dos artefatos
(`ExportWriter`, ja escreve metadata.json/metadata.txt/ready-to-post.txt sozinho) e o
checkpoint editorial (`ReviewQueue`, mesmo `REVIEW_PENDING` do pipeline principal). As
etapas exclusivas do rebrand (flash periodico da imagem de outro sobre o video, prender
a thumbnail como 1o frame, outro estatico no final) continuam vindo de
`clipador.export.periodic_flash`/`thumbnail_frame`/`outro_appender`.

Isolamento de erro por video usa o mesmo padrao de `clipador.pipeline` (`ClipStageError`
+ `_run` envolvendo cada etapa de risco, `ClipFailure` acumulado por clipe): um video
falhar numa etapa nao derruba os demais do lote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from clipador import category as category_module
from clipador.export.eleitoral import render_disclaimer_image
from clipador.export.models import ClipOutput
from clipador.export.outro_appender import OutroImageAppender
from clipador.export.periodic_flash import PeriodicImageFlasher
from clipador.export.review import ReviewQueue
from clipador.export.thumbnail_frame import ThumbnailFramePrepender
from clipador.export.watermark import WatermarkOverlay
from clipador.export.writer import ExportWriter
from clipador.kb.knowledge import KnowledgeBase
from clipador.metadata.generator import generate_metadata
from clipador.pipeline import ClipFailure, ClipStageError, _run, clip_excerpt, slugify_title
from clipador.progress import OnProgress, noop_progress
from clipador.reframe.faces import MediaPipeFaceDetector
from clipador.select.models import SHORT_FORMAT, ClipCandidate
from clipador.thumbnail.ai_thumbnail import build_thumbnail_generator
from clipador.thumbnail.background import build_background_editor
from clipador.thumbnail.builder import ThumbnailBuilder
from clipador.thumbnail.composer import ThumbnailComposer
from clipador.thumbnail.cutout import PersonCutout
from clipador.thumbnail.face_quality import FaceQualityScorer
from clipador.transcribe.models import TranscriptionResult
from clipador.transcribe.whisper import FasterWhisperTranscriber

DEFAULT_OUTRO_IMAGE = Path(__file__).resolve().parents[3] / "assets" / "rebrand" / "outro_censurado.jpg"
DEFAULT_OUTRO_DURATION_SECONDS = 5.0

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}

# Nao ha selecao automatica de candidato aqui (o video inteiro fornecido pelo usuario
# vira o "clipe"), valor fixo so pra manter o schema de ClipCandidate coerente com o
# resto do pipeline (ex.: ordenacao por score usada em outros lugares do repo).
REBRAND_CANDIDATE_SCORE = 70


@dataclass
class RebrandBatchResult:
    batch_folder: str
    clips: list[ClipOutput] = field(default_factory=list)
    failures: list[ClipFailure] = field(default_factory=list)


def discover_videos(input_dir: Path) -> list[Path]:
    """Videos de VIDEO_EXTENSIONS diretamente na pasta (nao recursivo), ordenados por
    nome para determinismo (ordem estavel entre rodadas, e a base do `--limit`)."""
    return sorted(
        (
            path
            for path in input_dir.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ),
        key=lambda path: path.name,
    )


def _default_thumbnail_builder(
    enable_thumbnail_composition: bool,
    face_model_path: Path | None,
    category: str = category_module.DEFAULT_CATEGORY,
) -> ThumbnailBuilder:
    face_scorer = FaceQualityScorer(face_detector=MediaPipeFaceDetector(model_path=face_model_path))
    if not enable_thumbnail_composition:
        return ThumbnailBuilder(face_scorer=face_scorer)
    composer = ThumbnailComposer(
        cutout=PersonCutout(),
        background_editor=build_background_editor(category),
        face_detector=MediaPipeFaceDetector(model_path=face_model_path),
        ai_generator=build_thumbnail_generator(category),
    )
    return ThumbnailBuilder(composer=composer, face_scorer=face_scorer)


def _build_candidate(transcription: TranscriptionResult) -> ClipCandidate:
    """Sintetiza um `ClipCandidate` cobrindo o video INTEIRO: nao ha selecao automatica
    de trecho aqui, o clipe e o video de entrada completo."""
    words = transcription.words
    if not words:
        raise ValueError("Transcricao sem nenhuma palavra reconhecida")
    return ClipCandidate(
        start_word_id=words[0].id,
        end_word_id=words[-1].id,
        format=SHORT_FORMAT,
        score=REBRAND_CANDIDATE_SCORE,
        justificativa=(
            "Video existente fornecido pelo usuario para rebranding (fora da selecao "
            "automatica do pipeline principal)."
        ),
        start=0.0,
        end=transcription.duration if transcription.duration is not None else words[-1].end,
    )


def _process_video(
    video_path: Path,
    batch_folder: str,
    clip_id: str,
    stage_dir: Path,
    kb: KnowledgeBase,
    outro_image: Path,
    transcriber: Any,
    metadata_client: Any,
    thumbnail_builder: ThumbnailBuilder,
    flasher: PeriodicImageFlasher,
    frame_prepender: ThumbnailFramePrepender,
    outro_appender: OutroImageAppender,
    writer: ExportWriter,
    review_queue: ReviewQueue,
    category: str = category_module.DEFAULT_CATEGORY,
    eleitoral_image_path: Path | None = None,
    eleitoral_overlay: WatermarkOverlay | None = None,
) -> ClipOutput:
    transcription = _run("transcribe", transcriber.transcribe, video_path)

    candidate = _run("candidate", _build_candidate, transcription)

    metadata = _run(
        "metadata",
        generate_metadata,
        candidate,
        clip_excerpt(transcription, candidate.start_word_id, candidate.end_word_id),
        kb,
        metadata_client,
        category=category,
    )

    thumbnail_path = stage_dir / "thumbnail.png"
    _run(
        "thumbnail",
        thumbnail_builder.build,
        video_path,
        thumbnail_path,
        stage_dir / "thumbnail_frames",
        headline=metadata.thumbnail_headline,
    )

    with_flashes = stage_dir / "with_flashes.mp4"
    _run("flash_periodico", flasher.apply, video_path, outro_image, with_flashes)

    with_frame = stage_dir / "with_thumbnail_frame.mp4"
    _run("thumbnail_frame", frame_prepender.prepend, with_flashes, thumbnail_path, with_frame)

    # Tarja de propaganda eleitoral entra depois de prender a capa e ANTES do outro
    # final: ela precisa cobrir o video de conteudo (incluindo a previa/capa, que aqui,
    # diferente do pipeline principal, ja faz parte do proprio arquivo de video), mas nao
    # o quadro estatico de encerramento, que e identidade do canal, nao conteudo.
    current = with_frame
    if eleitoral_image_path is not None and eleitoral_overlay is not None:
        current = _run(
            "eleitoral",
            eleitoral_overlay.apply,
            current,
            eleitoral_image_path,
            stage_dir / "eleitoral.mp4",
        )

    final_video = stage_dir / "with_outro.mp4"
    _run("outro", outro_appender.append, current, outro_image, final_video)

    output = _run(
        "export",
        writer.write,
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
    return _run("review", review_queue.enqueue, output)


def rebrand_batch(
    input_dir: Path,
    kb: KnowledgeBase,
    *,
    output_root: Path = Path("output"),
    work_dir: Path = Path(".clipador"),
    batch_name: str | None = None,
    outro_image: Path = DEFAULT_OUTRO_IMAGE,
    outro_duration_seconds: float = DEFAULT_OUTRO_DURATION_SECONDS,
    enable_thumbnail_composition: bool = True,
    face_model_path: Path | None = Path("models/blaze_face_short_range.tflite"),
    limit: int | None = None,
    transcriber: Any | None = None,
    metadata_client: Any | None = None,
    thumbnail_builder: ThumbnailBuilder | None = None,
    flasher: PeriodicImageFlasher | None = None,
    frame_prepender: ThumbnailFramePrepender | None = None,
    outro_appender: OutroImageAppender | None = None,
    writer: ExportWriter | None = None,
    review_queue: ReviewQueue | None = None,
    category: str = category_module.DEFAULT_CATEGORY,
    eleitoral_text: str = "",
    eleitoral_overlay: WatermarkOverlay | None = None,
    on_progress: OnProgress = noop_progress,
) -> RebrandBatchResult:
    category_module.validate_category(category)
    batch_folder = batch_name or f"rebrand_{slugify_title(input_dir.name) or input_dir.name}"

    videos = discover_videos(input_dir)
    if limit is not None:
        videos = videos[:limit]
    on_progress(
        {"event": "plan", "total": len(videos), "message": f"{len(videos)} video(s) no lote"}
    )

    transcriber = transcriber or FasterWhisperTranscriber()
    writer = writer or ExportWriter(output_root)
    review_queue = review_queue or ReviewQueue()
    thumbnail_builder = thumbnail_builder or _default_thumbnail_builder(
        enable_thumbnail_composition, face_model_path, category
    )
    flasher = flasher or PeriodicImageFlasher()
    frame_prepender = frame_prepender or ThumbnailFramePrepender()
    outro_appender = outro_appender or OutroImageAppender(duration_seconds=outro_duration_seconds)

    # So constroi o overlay (e renderiza o PNG) quando a tarja esta de fato ligada -
    # rebrand nao tem campo de feature-flag tipo o `watermark: WatermarkImages | None`
    # do pipeline principal, entao a checagem do texto e o proprio flag aqui. O overlay
    # e injetavel (mesmo padrao de flasher/frame_prepender) pra suite de testes conseguir
    # trocar o `runner`/`frame_sampler` por fakes sem chamar ffmpeg de verdade.
    eleitoral_image_path: Path | None = None
    if eleitoral_text.strip():
        eleitoral_overlay = eleitoral_overlay or WatermarkOverlay()
        eleitoral_image_path = render_disclaimer_image(
            eleitoral_text,
            work_dir / "eleitoral.png",
            frame_width=1080,
            frame_height=1920,
        )
    else:
        eleitoral_overlay = None

    result = RebrandBatchResult(batch_folder=batch_folder)
    total_videos = len(videos)

    for position, video_path in enumerate(videos, start=1):
        clip_id = slugify_title(video_path.stem) or video_path.stem
        stage_dir = work_dir / batch_folder / clip_id
        stage_dir.mkdir(parents=True, exist_ok=True)
        on_progress(
            {
                "event": "clip_start",
                "clip_id": clip_id,
                "format": SHORT_FORMAT,
                "index": position,
                "total": total_videos,
                "message": f"Rebrandeando {position}/{total_videos}: {video_path.name}",
            }
        )
        try:
            output = _process_video(
                video_path,
                batch_folder,
                clip_id,
                stage_dir,
                kb,
                outro_image,
                transcriber,
                metadata_client,
                thumbnail_builder,
                flasher,
                frame_prepender,
                outro_appender,
                writer,
                review_queue,
                category,
                eleitoral_image_path,
                eleitoral_overlay,
            )
        except ClipStageError as exc:
            result.failures.append(ClipFailure(clip_id, exc.stage, exc.message))
            on_progress(
                {
                    "event": "clip_failed",
                    "clip_id": clip_id,
                    "format": SHORT_FORMAT,
                    "stage": exc.stage,
                    "message": exc.message,
                    "index": position,
                    "total": total_videos,
                }
            )
        else:
            result.clips.append(output)
            on_progress(
                {
                    "event": "clip_done",
                    "clip_id": clip_id,
                    "format": SHORT_FORMAT,
                    "directory": str(output.directory),
                    "status": output.review_status,
                    "index": position,
                    "total": total_videos,
                    "message": f"Rebrand {position}/{total_videos} concluido",
                }
            )

    return result
