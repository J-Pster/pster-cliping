"""Deteccao de cena (PySceneDetect) isolada atras de uma interface trocavel."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Callable, Protocol

from clipador.reframe.models import Scene


class SceneDetector(Protocol):
    def detect_scenes(self, video_path: str | Path) -> list[Scene]: ...


def build_scenes(raw_scenes: Iterable[Any]) -> list[Scene]:
    """Converte pares (start, end) de FrameTimecode do PySceneDetect no schema do projeto."""
    scenes: list[Scene] = []
    for index, raw in enumerate(raw_scenes):
        start, end = raw
        scenes.append(
            Scene(
                index=index,
                start_frame=int(start.get_frames()),
                end_frame=int(end.get_frames()),
                start_time=float(start.get_seconds()),
                end_time=float(end.get_seconds()),
            )
        )
    return scenes


def sample_frame_indices(scene: Scene, count: int) -> list[int]:
    """Amostra `count` frames distribuidos dentro da cena, evitando os frames de transicao."""
    if count <= 0 or scene.frame_count <= 0:
        return []
    step = scene.frame_count / count
    return [
        min(scene.end_frame - 1, scene.start_frame + int((i + 0.5) * step)) for i in range(count)
    ]


def sample_times(scene: Scene, count: int) -> list[float]:
    """Instantes (em segundos) correspondentes a `sample_frame_indices`, para o crop variar no tempo."""
    if count <= 0 or scene.duration <= 0:
        return []
    step = scene.duration / count
    return [scene.start_time + (i + 0.5) * step for i in range(count)]


def _default_detect(video_path: str, threshold: float, min_scene_len: int) -> Sequence[Any]:
    from scenedetect import ContentDetector, detect

    return detect(video_path, ContentDetector(threshold=threshold, min_scene_len=min_scene_len))


class PySceneDetector:
    """Wrapper sobre `scenedetect`, com import lazy para nao exigir a lib nos testes."""

    def __init__(
        self,
        threshold: float = 27.0,
        min_scene_len: int = 15,
        detect_fn: Callable[[str, float, int], Sequence[Any]] = _default_detect,
    ) -> None:
        self.threshold = threshold
        self.min_scene_len = min_scene_len
        self._detect_fn = detect_fn

    def detect_scenes(self, video_path: str | Path) -> list[Scene]:
        raw = self._detect_fn(str(video_path), self.threshold, self.min_scene_len)
        return build_scenes(raw or [])
