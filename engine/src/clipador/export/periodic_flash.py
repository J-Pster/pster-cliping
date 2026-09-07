"""Sobrepoe periodicamente a imagem de outro por cima do video, como uma marca d'agua
rapida de reforco de marca (etapa exclusiva do rebrand, formato curto/vertical).

Diferente de `thumbnail_frame.py`/`outro_appender.py` (que INSEREM um segmento novo na
timeline via `concat`, cortando a reproducao), esta classe faz um OVERLAY: o video e o
audio continuam rodando normalmente, sem interrupcao, e a imagem so aparece por cima por
uma fracao de segundo antes de sumir de novo.

Decisao do usuario: flash de `flash_duration_seconds` a cada `interval_seconds`,
comecando em `interval_seconds` (nao em t=0) para nao cobrir o gancho inicial do video
logo no primeiro segundo - ciclo puramente periodico depois disso (10s, 20s, 30s, ...
ate o fim do video, com os valores default).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from clipador.ffmpeg_codec import video_encode_flags
from clipador.reframe.frames import FrameSampler, OpenCvFrameSampler

DEFAULT_INTERVAL_SECONDS = 10.0
DEFAULT_FLASH_DURATION_SECONDS = 0.3


class PeriodicFlashError(RuntimeError):
    pass


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


class PeriodicImageFlasher:
    """Sobrepoe a imagem de outro no video a cada `interval_seconds`, por
    `flash_duration_seconds` cada vez, via ffmpeg."""

    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        video_codec: str = "libx264",
        crf: int = 20,
        preset: str = "medium",
        audio_codec: str = "aac",
        frame_sampler: FrameSampler | None = None,
        runner: Callable[..., Any] = subprocess.run,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        flash_duration_seconds: float = DEFAULT_FLASH_DURATION_SECONDS,
        skip_first_flash: bool = True,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.video_codec = video_codec
        self.crf = crf
        self.preset = preset
        self.audio_codec = audio_codec
        self.frame_sampler = frame_sampler or OpenCvFrameSampler()
        self.runner = runner
        self.interval_seconds = interval_seconds
        self.flash_duration_seconds = flash_duration_seconds
        self.skip_first_flash = skip_first_flash

    def build_command(
        self,
        video_path: str | Path,
        image_path: str | Path,
        output_path: str | Path,
        width: int,
        height: int,
    ) -> list[str]:
        interval = _format_number(self.interval_seconds)
        flash_duration = _format_number(self.flash_duration_seconds)
        # Multiplicacao funciona como AND logico em expressoes ffmpeg (1*1=1, 0*x=0):
        # o clausulo extra so entra quando skip_first_flash pede pra pular o flash de t=0.
        skip_clause = f"*gte(t,{interval})" if self.skip_first_flash else ""
        filter_complex = (
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[img];"
            "[0:v][img]overlay=0:0:enable="
            f"'between(mod(t\\,{interval}),0,{flash_duration}){skip_clause}',"
            "format=yuv420p[outv]"
        )
        return [
            self.ffmpeg_binary,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(image_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "0:a",
            *video_encode_flags(self.video_codec, self.crf, self.preset),
            "-c:a",
            "copy",
            str(output_path),
        ]

    def apply(
        self,
        video_path: str | Path,
        image_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        video_path = Path(video_path)
        image_path = Path(image_path)
        output_path = Path(output_path)
        if not video_path.is_file():
            raise PeriodicFlashError(f"Video de entrada nao existe: {video_path}")
        if not image_path.is_file():
            raise PeriodicFlashError(f"Imagem de flash nao existe: {image_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width, height = self.frame_sampler.frame_size(video_path)

        command = self.build_command(video_path, image_path, output_path, width, height)
        self.runner(command, check=True)
        return output_path
