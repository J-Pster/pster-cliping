"""Deteccao de rosto: interface abstrata + implementacao MediaPipe (Tasks API).

A API legada `mediapipe.solutions.face_detection` foi removida por completo a partir do
mediapipe 1.0 (`hasattr(mediapipe, "solutions")` e `False` na versao instalada) - so resta
a Tasks API (`mediapipe.tasks.python.vision.FaceDetector`), a mesma familia de API ja usada
em `thumbnail/expression.py` pro Face Landmarker. Diferenca importante: a Tasks API devolve
`bounding_box` ja em pixels absolutos (`origin_x`/`origin_y`/`width`/`height`), nao mais
coordenadas relativas 0..1 como a API antiga - `faces_from_mediapipe` reflete isso.

Requer um modelo `.tflite` baixado a parte (nao vem no pip, igual o Face Landmarker):
`https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite`
(~220KB, mais leve que o Face Landmarker de proposito, ja que roda por amostra de frame
em todo o pipeline de reenquadramento - nao vale reusar o modelo pesado do thumbnail aqui).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from clipador.reframe.models import FaceBox, ReframeError


class FaceDetector(ABC):
    @abstractmethod
    def detect_faces(self, frame: Any) -> list[FaceBox]:
        """Recebe um frame (ndarray HxWxC) e devolve os rostos em pixels absolutos."""


def faces_from_mediapipe(detections: Any) -> list[FaceBox]:
    """Converte `Detection` da Tasks API (bounding_box ja em pixels absolutos) em `FaceBox`."""
    faces: list[FaceBox] = []
    for detection in detections or []:
        box = getattr(detection, "bounding_box", None)
        if box is None or box.width <= 0 or box.height <= 0:
            continue

        categories = getattr(detection, "categories", None) or []
        score = categories[0].score if categories else 1.0

        faces.append(
            FaceBox(
                x=float(box.origin_x),
                y=float(box.origin_y),
                width=float(box.width),
                height=float(box.height),
                confidence=float(score),
            )
        )
    return faces


def _default_image_factory(rgb_frame: Any) -> Any:
    import mediapipe as mp

    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)


class MediaPipeFaceDetector(FaceDetector):
    """MediaPipe Face Detector (Tasks API) com import lazy e detector injetavel.

    `model_path` e obrigatorio pra detectar de verdade (nao ha fallback silencioso aqui,
    diferente do Face Landmarker do thumbnail): sem um rosto detectado corretamente o
    reenquadramento nao tem o que seguir, entao um fallback neutro esconderia o problema
    em vez de avisar. Levanta `ReframeError` cedo se `model_path` nao existir.
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        min_detection_confidence: float = 0.5,
        convert_to_rgb: bool = True,
        detector_factory: Callable[[], Any] | None = None,
        image_factory: Callable[[Any], Any] = _default_image_factory,
    ) -> None:
        self.model_path = Path(model_path) if model_path is not None else None
        self.min_detection_confidence = min_detection_confidence
        self.convert_to_rgb = convert_to_rgb
        self._detector_factory = detector_factory
        self._image_factory = image_factory
        self._detector: Any | None = None

    def _load_default_detector(self) -> Any:
        if self.model_path is None or not self.model_path.is_file():
            raise ReframeError(
                "MediaPipeFaceDetector precisa de model_path apontando pro "
                "blaze_face_short_range.tflite (baixe em "
                "https://storage.googleapis.com/mediapipe-models/face_detector/"
                "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite)."
            )

        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        base_options = python.BaseOptions(model_asset_path=str(self.model_path))
        options = vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=self.min_detection_confidence,
        )
        return vision.FaceDetector.create_from_options(options)

    @property
    def detector(self) -> Any:
        if self._detector is None:
            factory = self._detector_factory or self._load_default_detector
            self._detector = factory()
        return self._detector

    def detect_faces(self, frame: Any) -> list[FaceBox]:
        # MediaPipe espera RGB; OpenCV entrega BGR.
        image_data = frame[:, :, ::-1] if self.convert_to_rgb else frame
        image = self._image_factory(image_data)
        result = self.detector.detect(image)
        return faces_from_mediapipe(getattr(result, "detections", None))
