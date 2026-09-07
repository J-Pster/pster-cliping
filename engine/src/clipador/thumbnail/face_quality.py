"""Score de qualidade de rosto: presenca + centralizacao, com expressao/olhos opcionais."""

from __future__ import annotations

from typing import Any

from clipador.reframe.faces import FaceDetector, MediaPipeFaceDetector
from clipador.thumbnail.expression import FaceLandmarkerScorer


class FaceQualityScorer:
    """Pontua um frame por rosto detectado, centralizacao e, opcionalmente, expressao/atencao.

    Sem `landmarker_scorer`, o comportamento e identico ao original: `confidence * centralizacao`.
    Com `landmarker_scorer`, o score base e combinado com eye_open/expression/frontality,
    ponderados pelos pesos `*_weight` (que juntos tomam espaco do peso do score base).
    """

    def __init__(
        self,
        face_detector: FaceDetector | None = None,
        landmarker_scorer: FaceLandmarkerScorer | None = None,
        eye_open_weight: float = 0.2,
        expression_weight: float = 0.15,
        frontality_weight: float = 0.15,
    ) -> None:
        self.face_detector = face_detector or MediaPipeFaceDetector()
        self.landmarker_scorer = landmarker_scorer
        self.eye_open_weight = eye_open_weight
        self.expression_weight = expression_weight
        self.frontality_weight = frontality_weight

    def score(self, frame: Any) -> float:
        """0.0 sem rosto; caso contrario `confidence * centralizacao`, opcionalmente combinado
        com expressao/olhos/frontalidade quando um `landmarker_scorer` foi injetado."""
        faces = self.face_detector.detect_faces(frame)
        if not faces:
            return 0.0

        height, width = frame.shape[:2]
        face = max(faces, key=lambda candidate: candidate.area)

        offset_x = abs(face.center_x - width / 2) / (width / 2)
        offset_y = abs(face.center_y - height / 2) / (height / 2)
        centering = max(0.0, 1.0 - (offset_x + offset_y) / 2)

        base_score = centering * face.confidence

        if self.landmarker_scorer is None:
            return base_score

        expression = self.landmarker_scorer.score(frame)
        expression_weight_total = (
            self.eye_open_weight + self.expression_weight + self.frontality_weight
        )
        base_weight = max(0.0, 1.0 - expression_weight_total)

        return (
            base_score * base_weight
            + expression.eye_open_score * self.eye_open_weight
            + expression.expression_score * self.expression_weight
            + expression.frontality_score * self.frontality_weight
        )
