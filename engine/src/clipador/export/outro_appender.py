"""Concatena uma imagem estatica como outro/encerramento no FINAL do video final do
clipe (feature de rebrand, formato curto/vertical).

Motivo: quando um video curto ja existente e "rebrandeado" fora do pipeline principal,
o encerramento com uma imagem fixa (ex.: aviso de "censurado", marca, chamada pra acao)
precisa aparecer como os ultimos segundos do arquivo final, nao como um overlay.

A mesma logica de casar SAR (sample aspect ratio) e fps entre a imagem estatica e o
video real, ja resolvida em `clipador.export.thumbnail_frame.ThumbnailFramePrepender`
(bug real ja caçado: sem `setsar=1` nos DOIS branches do filtro, video fonte com SAR
nao-quadrado tem SAR diferente da imagem e o `concat` recusa por mismatch de
parametros), e reaplicada aqui, so com a ordem invertida (video primeiro, imagem
depois) e a duracao trocada de 1 frame para `duration_seconds` segundos.

Duracao default de 5 segundos: decisao de negocio, configuravel porque o usuario troca
a imagem de outro (e possivelmente a duracao) com o tempo.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from clipador.ffmpeg_codec import video_encode_flags
from clipador.reframe.frames import FrameSampler, OpenCvFrameSampler

DEFAULT_AUDIO_SAMPLE_RATE = 48000
DEFAULT_DURATION_SECONDS = 5.0


class OutroAppendError(RuntimeError):
    pass


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


class OutroImageAppender:
    """Concatena a imagem de outro como `duration_seconds` segundos depois do video, via ffmpeg."""

    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        video_codec: str = "libx264",
        crf: int = 20,
        preset: str = "medium",
        audio_codec: str = "aac",
        audio_sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
        frame_sampler: FrameSampler | None = None,
        runner: Callable[..., Any] = subprocess.run,
        duration_seconds: float = DEFAULT_DURATION_SECONDS,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.video_codec = video_codec
        self.crf = crf
        self.preset = preset
        self.audio_codec = audio_codec
        self.audio_sample_rate = audio_sample_rate
        self.frame_sampler = frame_sampler or OpenCvFrameSampler()
        self.runner = runner
        self.duration_seconds = duration_seconds

    def build_command(
        self,
        video_path: str | Path,
        image_path: str | Path,
        output_path: str | Path,
        width: int,
        height: int,
        fps: float,
    ) -> list[str]:
        duration = _format_number(self.duration_seconds)
        filter_complex = (
            "[0:v]format=yuv420p,setsar=1[vid];"
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={_format_number(fps)},"
            f"format=yuv420p,trim=duration={duration},setpts=PTS-STARTPTS[img];"
            "[vid][img]concat=n=2:v=1:a=0[outv];"
            f"[0:a]aformat=sample_rates={self.audio_sample_rate}:channel_layouts=stereo[a0];"
            f"anullsrc=channel_layout=stereo:sample_rate={self.audio_sample_rate}:"
            f"duration={duration}[silence];"
            "[a0][silence]concat=n=2:v=0:a=1[outa]"
        )
        return [
            self.ffmpeg_binary,
            "-y",
            "-i",
            str(video_path),
            "-loop",
            "1",
            "-framerate",
            _format_number(fps),
            "-i",
            str(image_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            *video_encode_flags(self.video_codec, self.crf, self.preset),
            "-c:a",
            self.audio_codec,
            str(output_path),
        ]

    def append(
        self,
        video_path: str | Path,
        image_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        video_path = Path(video_path)
        image_path = Path(image_path)
        output_path = Path(output_path)
        if not video_path.is_file():
            raise OutroAppendError(f"Video de entrada nao existe: {video_path}")
        if not image_path.is_file():
            raise OutroAppendError(f"Imagem de outro nao existe: {image_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width, height = self.frame_sampler.frame_size(video_path)
        _frame_count, fps = self.frame_sampler.frame_count_and_fps(video_path)

        command = self.build_command(video_path, image_path, output_path, width, height, fps)
        self.runner(command, check=True)
        return output_path
