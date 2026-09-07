"""Leitura amostrada de frames via OpenCV, isolada atras de uma interface trocavel."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable, Protocol

from clipador.reframe.models import ReframeError

# Constantes estaveis do OpenCV, replicadas aqui para nao exigir `import cv2` no import do modulo.
CAP_PROP_POS_FRAMES = 1
CAP_PROP_FRAME_WIDTH = 3
CAP_PROP_FRAME_HEIGHT = 4
CAP_PROP_FPS = 5
CAP_PROP_FRAME_COUNT = 7


class FrameSampler(Protocol):
    def frame_size(self, video_path: str | Path) -> tuple[int, int]: ...

    def frame_count_and_fps(self, video_path: str | Path) -> tuple[int, float]: ...

    def read_frames(
        self, video_path: str | Path, frame_indices: Sequence[int]
    ) -> list[Any | None]: ...


def _default_capture_factory(video_path: str) -> Any:
    import cv2

    return cv2.VideoCapture(video_path)


class OpenCvFrameSampler:
    """Le apenas os frames amostrados por cena, com seek direto (nao decodifica o video inteiro)."""

    def __init__(
        self, capture_factory: Callable[[str], Any] = _default_capture_factory
    ) -> None:
        self._capture_factory = capture_factory

    def frame_size(self, video_path: str | Path) -> tuple[int, int]:
        capture = self._capture_factory(str(video_path))
        try:
            width = int(capture.get(CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(CAP_PROP_FRAME_HEIGHT))
        finally:
            capture.release()

        if width <= 0 or height <= 0:
            raise ReframeError(f"Nao foi possivel ler as dimensoes do video: {video_path}")
        return width, height

    def frame_count_and_fps(self, video_path: str | Path) -> tuple[int, float]:
        """Usado pra montar uma cena unica de fallback quando o scenedetect nao acha corte
        nenhum (plano continuo, comum em clipe curto de fala) - ver `VerticalReframer.plan`."""
        capture = self._capture_factory(str(video_path))
        try:
            frame_count = int(capture.get(CAP_PROP_FRAME_COUNT))
            fps = float(capture.get(CAP_PROP_FPS))
        finally:
            capture.release()

        if frame_count <= 0 or fps <= 0:
            raise ReframeError(
                f"Nao foi possivel ler frame_count/fps do video: {video_path}"
            )
        return frame_count, fps

    def read_frames(
        self, video_path: str | Path, frame_indices: Sequence[int]
    ) -> list[Any | None]:
        """Devolve um item por indice pedido, `None` onde o frame nao pode ser lido."""
        capture = self._capture_factory(str(video_path))
        frames: list[Any | None] = []
        try:
            for index in frame_indices:
                capture.set(CAP_PROP_POS_FRAMES, index)
                ok, frame = capture.read()
                frames.append(frame if ok else None)
        finally:
            capture.release()
        return frames
