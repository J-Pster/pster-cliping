"""Tipos base do reenquadramento vertical: cena, rosto e janela de crop."""

from __future__ import annotations

from dataclasses import dataclass


class ReframeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Scene:
    """Trecho continuo de video entre dois cortes, detectado na etapa de scene detection."""

    index: int
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float

    @property
    def frame_count(self) -> int:
        return max(0, self.end_frame - self.start_frame)

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)


@dataclass(frozen=True)
class FaceBox:
    """Rosto em coordenadas absolutas de pixel do frame original."""

    x: float
    y: float
    width: float
    height: float
    confidence: float = 1.0

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    @property
    def center(self) -> tuple[float, float]:
        return self.center_x, self.center_y


@dataclass(frozen=True)
class CropWindow:
    """Janela de recorte em pixels, ja no aspecto alvo e alinhada ao frame original."""

    x: int
    y: int
    width: int
    height: int

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    @property
    def ffmpeg_crop(self) -> str:
        return f"crop={self.width}:{self.height}:{self.x}:{self.y}"
