"""Marca d'agua do canal sobreposta ao clipe ja renderizado (etapa opcional do export).

Diferente de `periodic_flash.py` (que pisca uma imagem por fracoes de segundo) e de
`thumbnail_frame.py`/`outro_appender.py` (que INSEREM segmentos novos na timeline via
concat), aqui a imagem fica por cima do video inteiro, do primeiro ao ultimo frame, sem
cortar reproducao e sem tocar no audio.

A imagem esperada e um PNG com alfa **do tamanho do quadro inteiro**, com a marca ja
posicionada dentro dele - o mesmo arquivo que um editor de video usaria como camada.
Com isso a posicao da marca vira dado do asset, nao parametro de codigo: mudar de canto,
de tamanho ou de opacidade e trocar o PNG, sem mexer aqui.

Cada formato tem o seu arquivo. A moldura do 9:16 e a do 16:9 nao sao a mesma coisa:
uma marca desenhada pro horizontal seria esticada no vertical e cairia justamente sobre
a faixa de UI que Shorts/Reels/TikTok desenham por cima do video.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from clipador.ffmpeg_codec import video_encode_flags
from clipador.reframe.frames import FrameSampler, OpenCvFrameSampler
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT


class WatermarkError(RuntimeError):
    pass


@dataclass(frozen=True)
class WatermarkImages:
    """Os dois PNGs de marca d'agua, um por formato, validados na construcao.

    A existencia dos arquivos e checada UMA vez, aqui na fronteira. Depois de
    construido, o resto do pipeline confia no tipo e so pergunta qual arquivo usar
    para um formato, em vez de re-testar caminho a cada clipe.
    """

    short: Path
    long: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "short", Path(self.short))
        object.__setattr__(self, "long", Path(self.long))
        for label, path in (("curto", self.short), ("longo", self.long)):
            if not path.is_file():
                raise WatermarkError(f"Marca d'agua do formato {label} nao existe: {path}")

    def path_for(self, clip_format: str) -> Path:
        by_format = {SHORT_FORMAT: self.short, LONG_FORMAT: self.long}
        if clip_format not in by_format:
            raise WatermarkError(f"Formato sem marca d'agua definida: {clip_format!r}")
        return by_format[clip_format]


class WatermarkOverlay:
    """Sobrepoe o PNG da marca d'agua no video inteiro, via ffmpeg."""

    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        video_codec: str = "libx264",
        crf: int = 20,
        preset: str = "medium",
        frame_sampler: FrameSampler | None = None,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.video_codec = video_codec
        self.crf = crf
        self.preset = preset
        self.frame_sampler = frame_sampler or OpenCvFrameSampler()
        self.runner = runner

    def build_command(
        self,
        video_path: str | Path,
        image_path: str | Path,
        output_path: str | Path,
        width: int,
        height: int,
    ) -> list[str]:
        # O PNG entra como UM frame; `overlay` repete o ultimo frame do input curto
        # (eof_action=repeat, o default), entao a marca dura o video inteiro sem
        # precisar de `-loop 1`.
        #
        # O `pad` preenche com preto TRANSPARENTE (0x00000000), nao com o preto opaco
        # do default: um asset com aspecto diferente do quadro deixaria de sobrar
        # tarja e passaria a apagar a imagem. `format=rgba` preserva o alfa ate o
        # overlay; sem isso a marca entraria chapada, com fundo preto.
        filter_complex = (
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,"
            "format=rgba[wm];"
            "[0:v][wm]overlay=0:0:format=auto,format=yuv420p[outv]"
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
            raise WatermarkError(f"Video de entrada nao existe: {video_path}")
        if not image_path.is_file():
            raise WatermarkError(f"Imagem de marca d'agua nao existe: {image_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        width, height = self.frame_sampler.frame_size(video_path)

        self.runner(self.build_command(video_path, image_path, output_path, width, height), check=True)
        return output_path
