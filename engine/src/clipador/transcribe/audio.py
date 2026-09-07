"""Extracao do audio do video antes de enviar para uma API de transcricao.

O pipeline entrega o CAMINHO DO VIDEO para o transcriber, o que e irrelevante para um
modelo local (ele decodifica em disco) mas caro para uma API: um vídeo de 60 min em
1080p tem 1 a 3 GB, e subir isso e a parte mais lenta da transcricao em nuvem, por uma
margem enorme.

O mesmo audio em Opus mono 16 kHz a 32 kbps da cerca de 14 MB por hora, ou seja duas
ordens de grandeza a menos, sem perda relevante de qualidade de reconhecimento: 16 kHz e
a taxa em que os proprios modelos de ASR trabalham internamente, entao mandar mais do que
isso e enviar dado que o modelo descarta.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Taxa nativa dos modelos de ASR (Whisper, wav2vec2, e as APIs comerciais). Enviar 44.1kHz
# nao melhora nada: o primeiro passo do modelo e reamostrar para 16k.
SAMPLE_RATE = 16_000
# 32 kbps em Opus mono e transparente para fala. Abaixo disso comeca a aparecer artefato
# em sibilante, que e exatamente o que confunde o reconhecimento.
BITRATE = "32k"

# Extensoes que ja sao audio comprimido: nao ha o que extrair, o arquivo vai como esta.
AUDIO_SUFFIXES = frozenset({".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav", ".webm"})


def needs_extraction(path: str | Path) -> bool:
    return Path(path).suffix.lower() not in AUDIO_SUFFIXES


def probe_duration_seconds(
    path: str | Path, runner: Callable[..., Any] = subprocess.run
) -> float | None:
    """Duracao do arquivo em segundos, via ffprobe. `None` quando nao da pra determinar.

    Serve pra dimensionar o timeout da chamada de transcricao em nuvem: um video de 10
    minutos e um de 3 horas nao podem ter o mesmo teto de espera. `None` nao e erro, e
    "nao sei" - o chamador cai no teto conservador dele.
    """
    result = runner(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        return float(str(getattr(result, "stdout", "")).strip())
    except (TypeError, ValueError):
        logger.warning("ffprobe nao devolveu duracao para %s", path)
        return None


def extract_audio(
    source_path: str | Path,
    output_path: str | Path,
    sample_rate: int = SAMPLE_RATE,
    bitrate: str = BITRATE,
    runner: Callable[..., Any] = subprocess.run,
) -> Path:
    """Extrai a trilha de audio para Opus mono, pronta para upload."""
    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-vn",  # descarta o video: e ele que faz o arquivo pesar
        "-ac",
        "1",  # mono: ASR nao usa estereo, e dois canais dobram o upload a toa
        "-ar",
        str(sample_rate),
        "-c:a",
        "libopus",
        "-b:a",
        bitrate,
        str(output_path),
    ]
    logger.info("Extraindo audio de %s para %s (%dHz mono, %s)", source_path, output_path, sample_rate, bitrate)
    runner(cmd, check=True, capture_output=True)
    return output_path
