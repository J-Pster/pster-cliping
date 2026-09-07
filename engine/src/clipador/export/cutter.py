"""Corte do trecho escolhido no video de origem, com reencode H.264 (etapa [10]).

Alem do corte exato, aplica duas melhorias de pos-producao de audio direto no
mesmo comando ffmpeg (sem passo extra, sem reencode duplo):

- **Fade curto nas bordas** (`afade`): evita o "pop"/corte seco de audio que um
  corte cru produz quando a onda nao esta em zero-crossing no ponto exato do
  `start`/`end`. 30ms e curto o suficiente pra ser imperceptivel como fade e
  longo o suficiente pra eliminar o estalo.
- **Normalizacao de loudness** (`loudnorm`, EBU R128): garante volume
  consistente entre clipes de fontes/trechos diferentes. Alvo -16 LUFS, teto
  de pico -1.5 dBTP, faixa dinamica 11 LU - e o alvo comum a YouTube/Spotify e
  adequado a fala (nao musica). Aplicado em passe unico (nao two-pass): para
  clipes curtos, cortados de uma unica fonte ja gravada em nivel razoavelmente
  consistente, o ganho de precisao do two-pass nao compensa dobrar as chamadas
  de ffmpeg por clipe; se a qualidade de audio da fonte variar muito entre
  videos, two-pass fica como refinamento futuro (measure-pass + `linear=true`).

Padding de contexto (`pad_seconds`) estende o corte pra tras/pra frente do
`start`/`end` recebido, pensado pra ser chamado com um valor pequeno (dezenas
de ms) contra um corte que ja passou por `snap_to_silence` - o padding come
uma fatia do silencio real que already existe ali, nao invade fala adjacente
contanto que fique bem abaixo do gap minimo de silencio configurado na selecao
(default 300ms). Sem padding (`pad_seconds=0.0`, o default), o comportamento e
identico ao corte exato de antes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from clipador.ffmpeg_codec import hwaccel_decode_flags, video_encode_flags

DEFAULT_FADE_SECONDS = 0.03
DEFAULT_LOUDNORM_TARGET_I = -16.0
DEFAULT_LOUDNORM_TARGET_TP = -1.5
DEFAULT_LOUDNORM_TARGET_LRA = 11.0


def _format_seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def build_audio_filter(
    duration: float,
    fade_seconds: float = DEFAULT_FADE_SECONDS,
    loudnorm: bool = True,
    loudnorm_i: float = DEFAULT_LOUDNORM_TARGET_I,
    loudnorm_tp: float = DEFAULT_LOUDNORM_TARGET_TP,
    loudnorm_lra: float = DEFAULT_LOUDNORM_TARGET_LRA,
) -> str:
    """Filtro `-af` com fade nas bordas (se o clipe comportar) + loudnorm, cada um opcional."""
    stages: list[str] = []
    if fade_seconds > 0 and duration > fade_seconds * 2:
        fade_out_start = duration - fade_seconds
        stages.append(f"afade=t=in:st=0:d={_format_seconds(fade_seconds)}")
        stages.append(f"afade=t=out:st={_format_seconds(fade_out_start)}:d={_format_seconds(fade_seconds)}")
    if loudnorm:
        stages.append(f"loudnorm=I={loudnorm_i}:TP={loudnorm_tp}:LRA={loudnorm_lra}")
    return ",".join(stages)


class ClipCutter:
    """Extrai `start`-`end` do video de origem reencodando, para o corte ser exato no frame."""

    def __init__(
        self,
        ffmpeg_binary: str = "ffmpeg",
        crf: int = 20,
        preset: str = "medium",
        audio_codec: str = "aac",
        fade_seconds: float = DEFAULT_FADE_SECONDS,
        loudnorm: bool = True,
        video_codec: str = "libx264",
        input_decoder: str | None = None,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.ffmpeg_binary = ffmpeg_binary
        self.crf = crf
        self.preset = preset
        self.audio_codec = audio_codec
        self.fade_seconds = fade_seconds
        self.loudnorm = loudnorm
        self.video_codec = video_codec
        self.input_decoder = input_decoder
        self.runner = runner

    def build_command(
        self,
        video_path: str | Path,
        output_path: str | Path,
        start: float,
        end: float,
        pad_seconds: float = 0.0,
    ) -> list[str]:
        padded_start = max(0.0, start - pad_seconds)
        padded_end = end + pad_seconds if pad_seconds > 0 else end
        duration = max(0.0, padded_end - padded_start)

        command = [
            self.ffmpeg_binary,
            "-y",
            *hwaccel_decode_flags(self.input_decoder),
            "-ss",
            _format_seconds(padded_start),
            "-i",
            str(video_path),
            "-t",
            _format_seconds(duration),
            *video_encode_flags(self.video_codec, self.crf, self.preset),
        ]

        audio_filter = build_audio_filter(
            duration,
            fade_seconds=self.fade_seconds,
            loudnorm=self.loudnorm,
        )
        if audio_filter:
            command += ["-af", audio_filter]

        command += ["-c:a", self.audio_codec, str(output_path)]
        return command

    def cut(
        self,
        video_path: str | Path,
        output_path: str | Path,
        start: float,
        end: float,
        pad_seconds: float = 0.0,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = self.build_command(video_path, output_path, start, end, pad_seconds=pad_seconds)
        self.runner(command, check=True)
        return output_path
