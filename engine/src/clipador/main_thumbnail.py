"""Geracao standalone da thumbnail (+ titulo/descricao/hashtags) do VIDEO PRINCIPAL,
fora do fluxo de clipes.

Por que existe: alem dos cortes, o usuario tambem posta o video inteiro (a gravacao/live
original) e precisa de uma thumbnail pra ele. Desligado por padrao dentro do pipeline
principal (`PipelineConfig.generate_main_thumbnail`, ver `clipador.pipeline`), mas roda
sozinho via `generate_main_video_thumbnail()` / `clipador-main-thumbnail`, sem precisar
selecionar nem gerar nenhum clipe.

Reaproveita 100% do stack ja existente: um candidato sintetico cobrindo o video INTEIRO
(mesmo padrao de `clipador.rebrand.service._build_candidate`) alimenta `generate_metadata`,
e `ThumbnailBuilder` extrai o melhor frame direto do video de origem, sem cortar nada."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clipador import category as category_module
from clipador.export.writer import render_metadata_text, render_ready_to_post_text
from clipador.kb.knowledge import KnowledgeBase
from clipador.metadata.generator import generate_metadata
from clipador.metadata.models import ClipMetadata
from clipador.reframe.faces import MediaPipeFaceDetector
from clipador.select.models import LONG_FORMAT, ClipCandidate
from clipador.thumbnail.ai_thumbnail import build_thumbnail_generator
from clipador.thumbnail.background import build_background_editor
from clipador.thumbnail.builder import ThumbnailBuilder
from clipador.thumbnail.composer import ThumbnailComposer
from clipador.thumbnail.cutout import PersonCutout
from clipador.thumbnail.face_quality import FaceQualityScorer
from clipador.transcribe.models import TranscriptionResult
from clipador.transcribe.whisper import FasterWhisperTranscriber

THUMBNAIL_NAME = "thumbnail.png"
METADATA_TEXT_NAME = "metadata.txt"
METADATA_JSON_NAME = "metadata.json"
READY_TO_POST_NAME = "ready-to-post.txt"

# Mesmo valor fixo do rebrand (rebrand.service.REBRAND_CANDIDATE_SCORE): nao ha
# selecao/ranking aqui, o "candidato" e o video inteiro por definicao, so serve pra
# reaproveitar o schema de ClipCandidate que generate_metadata espera.
MAIN_VIDEO_CANDIDATE_SCORE = 70


@dataclass
class MainVideoThumbnailResult:
    metadata: ClipMetadata
    thumbnail_path: Path
    metadata_path: Path
    ready_to_post_path: Path


def build_main_video_candidate(transcription: TranscriptionResult) -> ClipCandidate:
    """Sintetiza um ClipCandidate cobrindo o video INTEIRO, so pra alimentar
    generate_metadata (mesmo padrao de rebrand.service._build_candidate). Formato sempre
    LONG_FORMAT: o video principal e sempre long-form, mesmo quando os cortes dele saem
    em short_9x16 tambem."""
    words = transcription.words
    if not words:
        raise ValueError("Transcricao sem nenhuma palavra reconhecida")
    return ClipCandidate(
        start_word_id=words[0].id,
        end_word_id=words[-1].id,
        format=LONG_FORMAT,
        score=MAIN_VIDEO_CANDIDATE_SCORE,
        justificativa="Video principal completo, fora da selecao automatica de cortes.",
        start=0.0,
        end=transcription.duration if transcription.duration is not None else words[-1].end,
    )


def _default_thumbnail_builder(category: str, face_model_path: Path | None) -> ThumbnailBuilder:
    face_scorer = FaceQualityScorer(face_detector=MediaPipeFaceDetector(model_path=face_model_path))
    composer = ThumbnailComposer(
        cutout=PersonCutout(),
        background_editor=build_background_editor(category),
        face_detector=MediaPipeFaceDetector(model_path=face_model_path),
        ai_generator=build_thumbnail_generator(category),
    )
    return ThumbnailBuilder(composer=composer, face_scorer=face_scorer)


def generate_main_video_thumbnail(
    video_path: str | Path,
    kb: KnowledgeBase,
    output_dir: str | Path,
    *,
    category: str = category_module.DEFAULT_CATEGORY,
    transcription: TranscriptionResult | None = None,
    transcriber: Any | None = None,
    metadata_client: Any | None = None,
    thumbnail_builder: ThumbnailBuilder | None = None,
    face_model_path: Path | None = Path("models/blaze_face_short_range.tflite"),
    frames_dir: str | Path | None = None,
) -> MainVideoThumbnailResult:
    """`transcription` e opcional: quem ja transcreveu o video (o pipeline principal, que
    roda isto so como etapa extra) passa o resultado pronto pra nao pagar a transcricao de
    novo; rodando isto sozinho (`clipador-main-thumbnail`), a transcricao roda aqui dentro."""
    category_module.validate_category(category)
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if transcription is None:
        transcription = (transcriber or FasterWhisperTranscriber()).transcribe(video_path)

    candidate = build_main_video_candidate(transcription)
    excerpt = " ".join(word.text for word in transcription.words)
    metadata = generate_metadata(candidate, excerpt, kb, metadata_client, category=category)

    thumbnail_builder = thumbnail_builder or _default_thumbnail_builder(category, face_model_path)
    thumbnail_path = output_dir / THUMBNAIL_NAME
    thumbnail_builder.build(
        video_path,
        thumbnail_path,
        frames_dir or (output_dir / "frames"),
        headline=metadata.thumbnail_headline,
    )

    metadata_path = output_dir / METADATA_TEXT_NAME
    metadata_path.write_text(render_metadata_text(metadata), encoding="utf-8")
    (output_dir / METADATA_JSON_NAME).write_text(
        json.dumps(metadata.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ready_to_post_path = output_dir / READY_TO_POST_NAME
    ready_to_post_path.write_text(
        render_ready_to_post_text(metadata.title, metadata.description, metadata.hashtags),
        encoding="utf-8",
    )

    return MainVideoThumbnailResult(
        metadata=metadata,
        thumbnail_path=thumbnail_path,
        metadata_path=metadata_path,
        ready_to_post_path=ready_to_post_path,
    )
