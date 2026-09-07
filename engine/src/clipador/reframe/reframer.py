"""Orquestracao do reenquadramento 9:16: cena -> rosto ativo -> janela de crop -> ffmpeg."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from clipador.ffmpeg_codec import hwaccel_decode_flags, video_encode_flags
from clipador.reframe.crop import CropWindowCalculator
from clipador.reframe.faces import FaceDetector, MediaPipeFaceDetector
from clipador.reframe.frames import FrameSampler, OpenCvFrameSampler
from clipador.reframe.models import CropWindow, FaceBox, ReframeError, Scene
from clipador.reframe.scenes import (
    PySceneDetector,
    SceneDetector,
    sample_frame_indices,
    sample_times,
)
from clipador.reframe.speaker import ActiveSpeakerDetector, LargestFaceHeuristic


@dataclass(frozen=True)
class CropKeyframe:
    time: float
    window: CropWindow


# O parser de expressao do ffmpeg (`if(lt(t,..` aninhado) quebra com "Invalid argument"
# a partir de ~100 niveis de aninhamento (confirmado empiricamente: 98 funciona, 100
# falha) - 80 da uma folga segura. Amostragem densa (2x/s) continua alimentando a
# suavizacao Kalman com mais dados, so o numero de keyframes que viram expressao do
# ffmpeg e limitado, distribuido entre as cenas do clipe.
MAX_EXPRESSION_KEYFRAMES_TOTAL = 80


def _decimate_keyframes(
    keyframes: tuple[CropKeyframe, ...], max_count: int
) -> tuple[CropKeyframe, ...]:
    """Reduz pra no maximo `max_count` keyframes, espacados uniformemente, sempre
    mantendo o primeiro e o ultimo (bordas da interpolacao). A trajetoria ja foi
    suavizada com todas as amostras antes disso - decimar so reduz quantos PONTOS da
    trajetoria ja suave viram expressao do ffmpeg, nao perde a suavizacao em si."""
    if len(keyframes) <= max_count:
        return keyframes
    if max_count < 2:
        return (keyframes[0], keyframes[-1])
    step = (len(keyframes) - 1) / (max_count - 1)
    indices = sorted({round(i * step) for i in range(max_count)})
    return tuple(keyframes[i] for i in indices)


@dataclass(frozen=True)
class ReframePlan:
    scene: Scene
    keyframes: tuple[CropKeyframe, ...]


@dataclass(frozen=True)
class ReframeResult:
    output_path: Path
    plans: tuple[ReframePlan, ...]
    command: tuple[str, ...]


def _format_time(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _piecewise_expr(keyframes: Sequence[CropKeyframe], axis: str) -> str:
    """Interpola LINEARMENTE entre keyframes consecutivos (`v0 + declive*(t-t0)`), em vez
    de um degrau instantaneo no valor anterior - o crop desliza continuamente de uma
    posicao a outra dentro de cada segmento em vez de pular de uma vez so no boundary.
    Antes do primeiro/depois do ultimo keyframe, mantem o valor da borda constante."""
    values = [getattr(keyframe.window, axis) for keyframe in keyframes]
    if len(set(values)) <= 1:
        return str(values[0])

    times = [keyframe.time for keyframe in keyframes]
    expr = str(values[-1])
    for i in range(len(values) - 2, -1, -1):
        t0, t1 = times[i], times[i + 1]
        v0, v1 = values[i], values[i + 1]
        if v0 == v1:
            segment_expr = str(v0)
        else:
            slope = (v1 - v0) / (t1 - t0)
            sign = "+" if slope >= 0 else "-"
            segment_expr = f"({v0}{sign}{_format_time(abs(slope))}*(t-{_format_time(t0)}))"
        boundary = _format_time(t1)
        expr = f"if(lt(t,{boundary}),{segment_expr},{expr})"
    return expr


def build_crop_filter(plans: Sequence[ReframePlan]) -> str:
    keyframes = sorted(
        (keyframe for plan in plans for keyframe in plan.keyframes), key=lambda k: k.time
    )
    if not keyframes:
        raise ReframeError("Nenhum keyframe de crop para montar o filtro do ffmpeg")

    window = keyframes[0].window
    x = _piecewise_expr(keyframes, "x")
    y = _piecewise_expr(keyframes, "y")
    x = f"'{x}'" if "if(" in x else x
    y = f"'{y}'" if "if(" in y else y
    return f"crop={window.width}:{window.height}:{x}:{y}"


class VerticalReframer:
    """Amostra frames por cena, segue o rosto ativo e aplica o crop 9:16 via ffmpeg."""

    def __init__(
        self,
        scene_detector: SceneDetector | None = None,
        face_detector: FaceDetector | None = None,
        speaker_detector: ActiveSpeakerDetector | None = None,
        frame_sampler: FrameSampler | None = None,
        # Amostra por INTERVALO DE TEMPO fixo, nao por contagem fixa por cena: uma
        # contagem fixa (ex.: 5 amostras) faz um clipe longo de 15min amostrar so a
        # cada ~3min, resultado visivel como "o crop demora e da uma ajustada de vez
        # em quando" - com intervalo fixo a densidade de amostragem escala com a
        # duracao da cena, entao o rastreamento reage mais rapido a mudanca de posicao
        # do rosto independente do tamanho do clipe. Reenquadramento so roda no formato
        # curto (VERTICAL_FORMATS), nunca no longo/16:9 - teto de ~90-120s por clipe,
        # entao 2x/s (medido: ~102ms/amostra, seek domina o custo) custa so uns 18s
        # extras por clipe curto, ~9s a mais que 1x/s.
        sample_interval_seconds: float = 0.5,
        min_samples_per_scene: int = 3,
        smoothing: float = 0.25,
        target_size: tuple[int, int] | None = (1080, 1920),
        ffmpeg_binary: str = "ffmpeg",
        crf: int = 20,
        preset: str = "medium",
        video_codec: str = "libx264",
        input_decoder: str | None = None,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.scene_detector = scene_detector or PySceneDetector()
        self.face_detector = face_detector or MediaPipeFaceDetector()
        self.speaker_detector = speaker_detector or LargestFaceHeuristic()
        self.frame_sampler = frame_sampler or OpenCvFrameSampler()
        self.sample_interval_seconds = sample_interval_seconds
        self.min_samples_per_scene = min_samples_per_scene
        self.smoothing = smoothing
        self.target_size = target_size
        self.ffmpeg_binary = ffmpeg_binary
        self.crf = crf
        self.preset = preset
        self.video_codec = video_codec
        self.input_decoder = input_decoder
        self.runner = runner

    def _samples_for_scene(self, scene: Scene) -> int:
        """Numero de amostras pra cobrir a cena a `sample_interval_seconds`, com piso
        `min_samples_per_scene` (cenas curtas ainda precisam de inicio/meio/fim)."""
        if scene.duration <= 0:
            return 0
        return max(self.min_samples_per_scene, round(scene.duration / self.sample_interval_seconds))

    def _active_faces(
        self, video_path: str | Path, frame_indices: Sequence[int]
    ) -> list[FaceBox | None]:
        frames = self.frame_sampler.read_frames(video_path, frame_indices)
        faces: list[FaceBox | None] = []
        for frame in frames:
            if frame is None:
                faces.append(None)
                continue
            detected = self.face_detector.detect_faces(frame)
            faces.append(self.speaker_detector.select_active_face(detected))
        return faces

    def plan(
        self, video_path: str | Path, scenes: Sequence[Scene] | None = None
    ) -> list[ReframePlan]:
        resolved = list(scenes) if scenes is not None else self.scene_detector.detect_scenes(video_path)
        if not resolved:
            if scenes is not None:
                # Cenas foram passadas explicitamente e vieram vazias: isso e erro do
                # chamador, nao caso de fallback.
                raise ReframeError(
                    f"Nenhuma cena detectada em {video_path}; passe `scenes` explicitamente"
                )
            # scenedetect nao achou corte nenhum - comum num clipe curto de plano unico
            # (fala continua, sem troca de camera). Trata como UMA cena cobrindo o clipe
            # inteiro, em vez de falhar: o reenquadramento ainda faz sentido, so nao tem
            # corte de camera pra reiniciar a suavizacao no meio.
            frame_count, fps = self.frame_sampler.frame_count_and_fps(video_path)
            resolved = [
                Scene(
                    index=0,
                    start_frame=0,
                    end_frame=frame_count,
                    start_time=0.0,
                    end_time=frame_count / fps,
                )
            ]

        frame_width, frame_height = self.frame_sampler.frame_size(video_path)
        calculator = CropWindowCalculator(frame_width, frame_height, smoothing=self.smoothing)

        # Orcamento de keyframes-que-viram-expressao-ffmpeg dividido entre as cenas do
        # clipe (ver MAX_EXPRESSION_KEYFRAMES_TOTAL) - a amostragem em si continua densa
        # por cena, so a decimacao antes de montar o filtro respeita o teto global.
        per_scene_cap = max(2, MAX_EXPRESSION_KEYFRAMES_TOTAL // max(1, len(resolved)))

        plans: list[ReframePlan] = []
        for scene in resolved:
            count = self._samples_for_scene(scene)
            indices = sample_frame_indices(scene, count)
            times = sample_times(scene, count)
            if not indices or not times:
                continue
            # A suavizacao reinicia a cada cena: num corte a mudanca de enquadramento e legitima.
            windows = calculator.calculate(self._active_faces(video_path, indices))
            keyframes = tuple(
                CropKeyframe(time=time, window=window) for time, window in zip(times, windows)
            )
            keyframes = _decimate_keyframes(keyframes, per_scene_cap)
            plans.append(ReframePlan(scene=scene, keyframes=keyframes))

        if not plans:
            raise ReframeError(f"Nenhuma cena de {video_path} rendeu amostras de frame")
        return plans

    def build_command(
        self, video_path: str | Path, output_path: str | Path, plans: Sequence[ReframePlan]
    ) -> list[str]:
        filters = [build_crop_filter(plans)]
        if self.target_size is not None:
            filters.append(f"scale={self.target_size[0]}:{self.target_size[1]}")

        return [
            self.ffmpeg_binary,
            "-y",
            *hwaccel_decode_flags(self.input_decoder),
            "-i",
            str(video_path),
            "-vf",
            ",".join(filters),
            *video_encode_flags(self.video_codec, self.crf, self.preset),
            "-c:a",
            "copy",
            str(output_path),
        ]

    def reframe(
        self,
        video_path: str | Path,
        output_path: str | Path,
        scenes: Sequence[Scene] | None = None,
    ) -> ReframeResult:
        plans = self.plan(video_path, scenes)
        command = self.build_command(video_path, output_path, plans)
        self.runner(command, check=True)
        return ReframeResult(
            output_path=Path(output_path),
            plans=tuple(plans),
            command=tuple(command),
        )
