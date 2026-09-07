"""Etapa 8: geração de thumbnail a partir do melhor frame do clipe."""

from clipador.thumbnail.ai_thumbnail import AIThumbnailGenerator, build_thumbnail_generator
from clipador.thumbnail.background import (
    GeminiBackgroundEditor,
    build_background_editor,
    fallback_treatment,
)
from clipador.thumbnail.builder import ThumbnailBuilder
from clipador.thumbnail.composer import ThumbnailComposer, ThumbnailStyle
from clipador.thumbnail.cutout import PersonCutout
from clipador.thumbnail.expression import ExpressionScore, FaceLandmarkerScorer
from clipador.thumbnail.extractor import IFrameExtractor
from clipador.thumbnail.face_quality import FaceQualityScorer
from clipador.thumbnail.models import ScoredFrame, ThumbnailError
from clipador.thumbnail.ranker import ThumbnailCandidateRanker
from clipador.thumbnail.sharpness import SharpnessScorer, score_sharpness

__all__ = [
    "AIThumbnailGenerator",
    "build_thumbnail_generator",
    "IFrameExtractor",
    "ThumbnailBuilder",
    "SharpnessScorer",
    "score_sharpness",
    "FaceQualityScorer",
    "ExpressionScore",
    "FaceLandmarkerScorer",
    "GeminiBackgroundEditor",
    "build_background_editor",
    "PersonCutout",
    "ScoredFrame",
    "ThumbnailCandidateRanker",
    "ThumbnailComposer",
    "ThumbnailError",
    "ThumbnailStyle",
    "fallback_treatment",
]
