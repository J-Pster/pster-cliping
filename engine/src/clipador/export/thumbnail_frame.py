"""Prende a thumbnail escolhida nos PRIMEIROS frames do video final do clipe curto (etapa
extra apos o burn-in de legenda, so pro formato vertical).

Motivo: varias plataformas (feed, preview antes do play, apps de terceiro tipo Buffer) usam
o frame 0 do proprio arquivo como thumbnail automatica quando nenhuma custom e setada via
API - prender o mesmo frame ja escolhido/composto pelo ThumbnailBuilder garante que essa
previa automatica bata com a thumbnail pretendida.

Duracao de exatamente `DEFAULT_PREPENDED_FRAME_COUNT` frames (decisao do usuario, 3 a 30fps
= 0.1s): mais de 1 frame porque alguns players/apps que geram a previa a partir de um frame
NAO o 0 (ex.: pulam alguns ms pra evitar frame preto) ainda caem dentro da thumbnail.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from clipador.ffmpeg_codec import video_encode_flags
from clipador.reframe.frames import FrameSampler, OpenCvFrameSampler

DEFAULT_AUDIO_SAMPLE_RATE = 48000
DEFAULT_PREPENDED_FRAME_COUNT = 3


class ThumbnailFramePrependError(RuntimeError):
    pass


def _format_number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


class ThumbnailFramePrepender:
    """Concatena a imagem da thumbnail como os `prepended_frame_count` primeiros frames
    do video, via ffmpeg."""

    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        video_codec: str = "libx264",
        crf: int = 20,
        preset: str = "medium",
        audio_codec: str = "aac",
        audio_sample_rate: int = DEFAULT_AUDIO_SAMPLE_RATE,
        prepended_frame_count: int = DEFAULT_PREPENDED_FRAME_COUNT,
        frame_sampler: FrameSampler | None = None,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.video_codec = video_codec
        self.crf = crf
        self.preset = preset
        self.audio_codec = audio_codec
        self.audio_sample_rate = audio_sample_rate
        self.prepended_frame_count = prepended_frame_count
        self.frame_sampler = frame_sampler or OpenCvFrameSampler()
        self.runner = runner

    def build_command(
        self,
        video_path: str | Path,
        thumbnail_path: str | Path,
        output_path: str | Path,
        width: int,
        height: int,
        fps: float,
    ) -> list[str]:
        frames_duration = self.prepended_frame_count / fps
        filter_complex = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={_format_number(fps)},"
            "format=yuv420p,"
            f"trim=start_frame=0:end_frame={self.prepended_frame_count},"
            "setpts=PTS-STARTPTS[img];"
            # setsar=1 tambem no video de entrada: sem isso, video fonte com SAR
            # nao-quadrado (comum em encode via NVENC) tem SAR diferente da imagem
            # (que sempre sai SAR 1:1) e o concat recusa por mismatch de parametros.
            "[1:v]format=yuv420p,setsar=1[vid];"
            "[img][vid]concat=n=2:v=1:a=0[outv];"
            f"anullsrc=channel_layout=stereo:sample_rate={self.audio_sample_rate}:"
            f"duration={_format_number(frames_duration)}[silence];"
            f"[1:a]aformat=sample_rates={self.audio_sample_rate}:channel_layouts=stereo[a1];"
            "[silence][a1]concat=n=2:v=0:a=1[outa]"
        )
        return [
            self.ffmpeg_binary,
            "-y",
            "-loop",
            "1",
            "-framerate",
            _format_number(fps),
            "-i",
            str(thumbnail_path),
            "-i",
            str(video_path),
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

    def prepend(
        self,
        video_path: str | Path,
        thumbnail_path: str | Path,
        output_path: str | Path,
    ) -> Path:
        video_path = Path(video_path)
        thumbnail_path = Path(thumbnail_path)
        output_path = Path(output_path)
        if not video_path.is_file():
            raise ThumbnailFramePrependError(f"Video de entrada nao existe: {video_path}")
        if not thumbnail_path.is_file():
            raise ThumbnailFramePrependError(f"Thumbnail nao existe: {thumbnail_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width, height = self.frame_sampler.frame_size(video_path)
        _frame_count, fps = self.frame_sampler.frame_count_and_fps(video_path)

        command = self.build_command(video_path, thumbnail_path, output_path, width, height, fps)
        self.runner(command, check=True)
        return output_path
