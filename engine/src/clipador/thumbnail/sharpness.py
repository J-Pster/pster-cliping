"""Score de nitidez de um frame via variancia do Laplaciano (lazy import de OpenCV)."""

from __future__ import annotations

from typing import Any, Callable


def _default_laplacian_variance(frame: Any) -> float:
    import cv2

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def score_sharpness(
    frame: Any, laplacian_variance: Callable[[Any], float] | None = None
) -> float:
    """Funcao pura: quanto maior o valor, mais nitido o frame."""
    calc = laplacian_variance or _default_laplacian_variance
    return calc(frame)


class SharpnessScorer:
    """Wrapper injetavel em torno de `score_sharpness`, no padrao dos demais scorers."""

    def __init__(self, laplacian_variance: Callable[[Any], float] | None = None) -> None:
        self._laplacian_variance = laplacian_variance or _default_laplacian_variance

    def score(self, frame: Any) -> float:
        return score_sharpness(frame, self._laplacian_variance)
