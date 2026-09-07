"""Score de expressao facial via MediaPipe Face Landmarker (Tasks API, blendshapes)."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

MODEL_DOWNLOAD_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)


@dataclass(frozen=True)
class ExpressionScore:
    """Sinais de expressao de um rosto, derivados dos 52 blendshapes do Face Landmarker.

    `eye_open_score`: 1.0 = olhos bem abertos, 0.0 = piscando/fechados.
    `expression_score`: 1.0 = expressao viva (boca aberta, sobrancelhas erguidas/franzidas,
    olhos arregalados), 0.0 = rosto neutro/inexpressivo.
    `frontality_score`: 1.0 = rosto de frente para a camera, 0.0 = perfil (~90 graus).
    """

    eye_open_score: float
    expression_score: float
    frontality_score: float


def _neutral_score() -> ExpressionScore:
    return ExpressionScore(eye_open_score=0.5, expression_score=0.5, frontality_score=0.5)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _frontality_from_matrix(matrix: Any) -> float:
    """Deriva frontalidade (1.0 frontal, cai com o angulo) do yaw/pitch da matriz de transformacao."""
    r00 = matrix[0][0]
    r10 = matrix[1][0]
    r20 = matrix[2][0]
    r21 = matrix[2][1]
    r22 = matrix[2][2]

    yaw = math.degrees(math.atan2(-r20, math.sqrt(r00**2 + r10**2)))
    pitch = math.degrees(math.atan2(r21, r22))
    angle = math.sqrt(yaw**2 + pitch**2)
    return _clamp01(1.0 - angle / 90.0)


class FaceLandmarkerScorer:
    """Pontua expressao facial via MediaPipe Face Landmarker (`output_face_blendshapes=True`).

    Requer o modelo `face_landmarker.task` (poucos MB), que NAO acompanha o pacote e
    precisa ser baixado manualmente pelo usuario a partir da URL oficial da Google:
    https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task

    Se `model_path` for None ou o arquivo apontado nao existir, o scorer opera em modo
    de fallback: devolve `ExpressionScore` neutro (0.5 em todos os campos) e loga um
    aviso, garantindo que o pipeline nunca quebre por falta do modelo.
    """

    def __init__(
        self,
        model_path: Path | None = None,
        landmarker_factory: Callable[[], Any] | None = None,
        image_factory: Callable[[Any], Any] | None = None,
        num_faces: int = 1,
    ) -> None:
        self.model_path = Path(model_path) if model_path is not None else None
        self.num_faces = num_faces
        self._landmarker_factory = landmarker_factory
        self._image_factory = image_factory or self._default_image_factory
        self._landmarker: Any | None = None
        self._available = self._landmarker_factory is not None or (
            self.model_path is not None and self.model_path.exists()
        )
        if not self._available:
            logger.warning(
                "FaceLandmarkerScorer sem modelo disponivel (%s); usando scores neutros. "
                "Baixe o modelo em %s",
                self.model_path,
                MODEL_DOWNLOAD_URL,
            )

    def _default_image_factory(self, frame: Any) -> Any:
        import mediapipe as mp

        return mp.Image(image_format=mp.ImageFormat.SRGB, data=frame[:, :, ::-1])

    def _load_default_landmarker(self) -> Any:
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import (
            FaceLandmarker,
            FaceLandmarkerOptions,
            RunningMode,
        )

        options = FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self.model_path)),
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            num_faces=self.num_faces,
            running_mode=RunningMode.IMAGE,
        )
        return FaceLandmarker.create_from_options(options)

    @property
    def landmarker(self) -> Any:
        if self._landmarker is None:
            factory = self._landmarker_factory or self._load_default_landmarker
            self._landmarker = factory()
        return self._landmarker

    def score(self, frame: Any) -> ExpressionScore:
        """Roda o Face Landmarker no frame; devolve score neutro sem modelo/rosto detectado."""
        if not self._available:
            return _neutral_score()

        image = self._image_factory(frame)
        result = self.landmarker.detect(image)

        blendshapes_list = getattr(result, "face_blendshapes", None)
        if not blendshapes_list:
            return _neutral_score()

        categories = {c.category_name: c.score for c in blendshapes_list[0]}

        eye_blink_left = categories.get("eyeBlinkLeft", 0.0)
        eye_blink_right = categories.get("eyeBlinkRight", 0.0)
        eye_open_score = _clamp01(1.0 - max(eye_blink_left, eye_blink_right))

        expression_raw = (
            0.3 * categories.get("jawOpen", 0.0)
            + 0.2 * categories.get("browInnerUp", 0.0)
            + 0.15 * categories.get("browDownLeft", 0.0)
            + 0.15 * categories.get("browDownRight", 0.0)
            + 0.1 * categories.get("eyeWideLeft", 0.0)
            + 0.1 * categories.get("eyeWideRight", 0.0)
        )
        expression_score = _clamp01(expression_raw / 0.6)

        matrices = getattr(result, "facial_transformation_matrixes", None)
        frontality_score = _frontality_from_matrix(matrices[0]) if matrices else 0.5

        return ExpressionScore(
            eye_open_score=eye_open_score,
            expression_score=expression_score,
            frontality_score=frontality_score,
        )
