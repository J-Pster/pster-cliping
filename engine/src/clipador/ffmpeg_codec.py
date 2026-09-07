"""Flags ffmpeg de encode/decode por codec, escolhidos por config explicita.

Nao ha deteccao automatica de hardware aqui: o chamador decide `video_codec`/
`input_decoder` (ex.: `run_test_video.py` liga NVENC/NVDEC porque sabe que a maquina
tem uma RTX). O default de cada classe que usa este modulo continua CPU
(`libx264`/decode por software), pra nao quebrar quem roda sem GPU NVIDIA.
"""

from __future__ import annotations


def video_encode_flags(codec: str, crf: int, preset: str) -> list[str]:
    """Flags de `-c:v` + controle de qualidade pro codec de saida escolhido."""
    if codec == "libx264":
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
    if codec == "h264_nvenc":
        # NVENC nao tem CRF; `-rc vbr -cq N` e o equivalente de qualidade constante.
        return ["-c:v", "h264_nvenc", "-preset", preset, "-rc", "vbr", "-cq", str(crf)]
    raise ValueError(f"Codec de video nao suportado: {codec!r}")


def hwaccel_decode_flags(decoder: str | None) -> list[str]:
    """Flags de hwaccel pra inserir ANTES do `-i` de entrada. None = decode por software."""
    if decoder is None:
        return []
    return ["-hwaccel", "cuda", "-c:v", decoder]
