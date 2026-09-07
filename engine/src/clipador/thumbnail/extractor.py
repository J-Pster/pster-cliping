"""Extracao de candidatos a thumbnail por I-frame, via comando ffmpeg injetavel."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Callable


def _format_seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


class IFrameExtractor:
    """Monta e roda o comando ffmpeg que extrai frames candidatos por I-frame de um trecho."""

    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.runner = runner

    def build_command(
        self,
        video_path: str | Path,
        output_pattern: str | Path,
        start: float | None = None,
        end: float | None = None,
    ) -> list[str]:
        command = [self.ffmpeg_binary, "-y"]
        if start is not None:
            command += ["-ss", _format_seconds(start)]
        command += ["-i", str(video_path)]
        if end is not None:
            duration = end - start if start is not None else end
            command += ["-t", _format_seconds(duration)]
        command += [
            "-vf",
            r"select=eq(pict_type\,I)",
            "-fps_mode",
            "vfr",
            str(output_pattern),
        ]
        return command

    def extract(
        self,
        video_path: str | Path,
        output_dir: str | Path,
        start: float | None = None,
        end: float | None = None,
        filename_pattern: str = "candidate_%03d.jpg",
    ) -> list[Path]:
        """Roda o comando via `runner` e devolve os candidatos ja escritos em `output_dir`."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        command = self.build_command(video_path, output_dir / filename_pattern, start, end)
        self.runner(command, check=True)

        glob_pattern = re.sub(r"%\d*d", "*", filename_pattern)
        return sorted(output_dir.glob(glob_pattern))
