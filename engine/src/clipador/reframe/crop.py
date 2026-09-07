"""Calculo da janela de crop 9:16 seguindo o rosto ativo, com suavizacao temporal."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from clipador.reframe.models import CropWindow, FaceBox, Scene

SmoothingStrategy = Literal["ema", "kalman_rts"]

Matrix = tuple[tuple[float, float], tuple[float, float]]
Vector = tuple[float, float]

_IDENTITY: Matrix = ((1.0, 0.0), (0.0, 1.0))
# Velocidade constante com passo unitario: a amostragem por cena e uniforme.
_TRANSITION: Matrix = ((1.0, 1.0), (0.0, 1.0))


def _even(value: int) -> int:
    """Dimensoes impares quebram encoders yuv420p; arredonda pra baixo no par mais proximo."""
    return max(2, value - (value % 2))


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _mat_mul(a: Matrix, b: Matrix) -> Matrix:
    return (
        (a[0][0] * b[0][0] + a[0][1] * b[1][0], a[0][0] * b[0][1] + a[0][1] * b[1][1]),
        (a[1][0] * b[0][0] + a[1][1] * b[1][0], a[1][0] * b[0][1] + a[1][1] * b[1][1]),
    )


def _mat_add(a: Matrix, b: Matrix) -> Matrix:
    return (
        (a[0][0] + b[0][0], a[0][1] + b[0][1]),
        (a[1][0] + b[1][0], a[1][1] + b[1][1]),
    )


def _mat_sub(a: Matrix, b: Matrix) -> Matrix:
    return (
        (a[0][0] - b[0][0], a[0][1] - b[0][1]),
        (a[1][0] - b[1][0], a[1][1] - b[1][1]),
    )


def _mat_transpose(a: Matrix) -> Matrix:
    return ((a[0][0], a[1][0]), (a[0][1], a[1][1]))


def _mat_inverse(a: Matrix) -> Matrix:
    determinant = a[0][0] * a[1][1] - a[0][1] * a[1][0]
    if determinant == 0.0:
        return _IDENTITY
    return (
        (a[1][1] / determinant, -a[0][1] / determinant),
        (-a[1][0] / determinant, a[0][0] / determinant),
    )


def scene_reset_indices(scenes: Sequence[Scene], times: Sequence[float]) -> list[int]:
    """Indices de `times` onde comeca uma cena nova, para reiniciar o suavizador no corte."""
    starts = sorted(scene.start_time for scene in scenes)
    resets: list[int] = []
    for start in starts:
        for index, time in enumerate(times):
            if time >= start:
                if index > 0 and index not in resets:
                    resets.append(index)
                break
    return sorted(resets)


@dataclass(frozen=True)
class KalmanRtsSmoother:
    """Suavizador offline de trajetoria 1D: passada Kalman (forward) + RTS (backward).

    O estado e [posicao, velocidade] com transicao de velocidade constante. Como o
    pipeline processa o clipe inteiro de uma vez, a passada RTS reaproveita as amostras
    futuras e devolve uma trajetoria sem o atraso sistematico da media movel exponencial.
    """

    process_noise: float = 1.0
    measurement_noise: float = 12.0
    initial_variance: float = 1e6

    @classmethod
    def from_alpha(cls, alpha: float) -> KalmanRtsSmoother:
        """Reaproveita o alfa da EMA: so a razao ruido de processo/medicao afeta o ganho.

        `alpha == 1` zera o ruido de medicao, o que faz o filtro colar nas medicoes
        (ganho 1, covariancia posterior nula) e reproduzir a trajetoria crua.
        """
        return cls(process_noise=1.0, measurement_noise=(1.0 - alpha) / (alpha * alpha))

    def smooth(self, values: Sequence[float]) -> list[float]:
        count = len(values)
        if count <= 1:
            return [float(value) for value in values]

        q = self.process_noise
        process = ((q / 3.0, q / 2.0), (q / 2.0, q))
        transition_t = _mat_transpose(_TRANSITION)
        r = self.measurement_noise

        predicted_states: list[Vector] = []
        predicted_covs: list[Matrix] = []
        filtered_states: list[Vector] = []
        filtered_covs: list[Matrix] = []

        state: Vector = (float(values[0]), 0.0)
        cov: Matrix = ((self.initial_variance, 0.0), (0.0, self.initial_variance))

        for value in values:
            predicted_states.append(state)
            predicted_covs.append(cov)

            innovation_cov = cov[0][0] + r
            gain = (cov[0][0] / innovation_cov, cov[1][0] / innovation_cov)
            residual = float(value) - state[0]
            state = (state[0] + gain[0] * residual, state[1] + gain[1] * residual)
            cov = _mat_mul(_mat_sub(_IDENTITY, ((gain[0], 0.0), (gain[1], 0.0))), cov)

            filtered_states.append(state)
            filtered_covs.append(cov)

            state = (state[0] + state[1], state[1])
            cov = _mat_add(_mat_mul(_mat_mul(_TRANSITION, cov), transition_t), process)

        smoothed: list[float] = [filtered_states[-1][0]]
        state = filtered_states[-1]
        cov = filtered_covs[-1]
        for index in range(count - 2, -1, -1):
            next_state = predicted_states[index + 1]
            next_cov = predicted_covs[index + 1]
            blend = _mat_mul(
                _mat_mul(filtered_covs[index], transition_t), _mat_inverse(next_cov)
            )
            delta = (state[0] - next_state[0], state[1] - next_state[1])
            state = (
                filtered_states[index][0] + blend[0][0] * delta[0] + blend[0][1] * delta[1],
                filtered_states[index][1] + blend[1][0] * delta[0] + blend[1][1] * delta[1],
            )
            cov = _mat_add(
                filtered_covs[index],
                _mat_mul(
                    _mat_mul(blend, _mat_sub(cov, next_cov)), _mat_transpose(blend)
                ),
            )
            smoothed.append(state[0])

        smoothed.reverse()
        return smoothed


@dataclass
class CropWindowCalculator:
    """Funcao pura de (sequencia de rostos) -> (sequencia de janelas de crop suavizadas).

    `smoothing` e o alfa da suavizacao: 1.0 segue o rosto sem amortecer nenhum pulo,
    valores baixos amortecem movimento brusco. Com `smoothing_strategy="kalman_rts"`
    (padrao) o amortecimento vem de um filtro de Kalman com passada RTS, que suaviza
    sem o atraso da media movel exponencial (`"ema"`).
    """

    frame_width: int
    frame_height: int
    aspect_width: int = 9
    aspect_height: int = 16
    smoothing: float = 0.25
    smoothing_strategy: SmoothingStrategy = "kalman_rts"

    def __post_init__(self) -> None:
        if self.frame_width <= 0 or self.frame_height <= 0:
            raise ValueError("Dimensoes do frame original precisam ser positivas")
        if not 0 < self.smoothing <= 1:
            raise ValueError("smoothing precisa estar em (0, 1]")
        if self.smoothing_strategy not in ("ema", "kalman_rts"):
            raise ValueError("smoothing_strategy precisa ser 'ema' ou 'kalman_rts'")

    def window_size(self) -> tuple[int, int]:
        height = self.frame_height
        width = round(height * self.aspect_width / self.aspect_height)
        if width > self.frame_width:
            width = self.frame_width
            height = round(width * self.aspect_height / self.aspect_width)
        return _even(width), _even(height)

    def window_for(self, center_x: float, center_y: float) -> CropWindow:
        width, height = self.window_size()
        return CropWindow(
            x=_clamp(round(center_x - width / 2), 0, self.frame_width - width),
            y=_clamp(round(center_y - height / 2), 0, self.frame_height - height),
            width=width,
            height=height,
        )

    def centers(self, faces: Sequence[FaceBox | None]) -> list[tuple[float, float]]:
        """Amostras sem rosto herdam o ultimo centro conhecido (ou o centro do frame)."""
        default = (self.frame_width / 2, self.frame_height / 2)
        last: tuple[float, float] | None = None
        resolved: list[tuple[float, float]] = []
        for face in faces:
            if face is not None:
                last = face.center
            resolved.append(default if last is None else last)
        return resolved

    def _segments(
        self, count: int, reset_indices: Sequence[int] | None
    ) -> list[tuple[int, int]]:
        bounds = sorted({0, count} | {i for i in (reset_indices or []) if 0 < i < count})
        return list(zip(bounds, bounds[1:]))

    def _smooth_ema(self, values: Sequence[float]) -> list[float]:
        alpha = self.smoothing
        smoothed: list[float] = []
        previous: float | None = None
        for value in values:
            current = value if previous is None else alpha * value + (1 - alpha) * previous
            smoothed.append(current)
            previous = current
        return smoothed

    def smooth(
        self,
        centers: Sequence[tuple[float, float]],
        reset_indices: Sequence[int] | None = None,
    ) -> list[tuple[float, float]]:
        """Suaviza a trajetoria do centro do crop, reiniciando o filtro em cada corte de cena.

        `reset_indices` sao posicoes em `centers` onde uma cena nova comeca: sem esse
        reset o suavizador arrasta o enquadramento atraves do corte, o artefato mais
        visivel do reenquadramento automatico.
        """
        if self.smoothing_strategy == "ema":
            smoother = self._smooth_ema
        else:
            smoother = KalmanRtsSmoother.from_alpha(self.smoothing).smooth

        smoothed: list[tuple[float, float]] = []
        for start, end in self._segments(len(centers), reset_indices):
            segment = centers[start:end]
            xs = smoother([center[0] for center in segment])
            ys = smoother([center[1] for center in segment])
            smoothed.extend(zip(xs, ys))
        return smoothed

    def calculate(
        self,
        faces: Sequence[FaceBox | None],
        reset_indices: Sequence[int] | None = None,
    ) -> list[CropWindow]:
        centers = self.smooth(self.centers(faces), reset_indices)
        return [self.window_for(x, y) for x, y in centers]
