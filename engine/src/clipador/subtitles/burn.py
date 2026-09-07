"""Escrita do .ass em disco e burn-in no video via ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from clipador.ffmpeg_codec import hwaccel_decode_flags, video_encode_flags


def save_ass(content: str, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _escape_filter_path(path: Path) -> str:
    """Escapa o path pro filtro `ass=` do ffmpeg (barras, dois-pontos de drive letter).

    So escapar o `:` com `\\:` nao basta no Windows: o parser de filtergraph do ffmpeg
    ainda tenta separar o resto da string como se fossem outras opcoes do filtro
    (`original_size`, etc), porque a letra de drive nao fecha o valor sem ambiguidade.
    Envolver o valor inteiro em aspas simples resolve - e o jeito documentado de passar
    um path com `:` pros filtros `ass`/`subtitles`. Confirmado rodando o comando de
    verdade contra um clipe real: sem aspas da erro `original_size ... Invalid argument`
    (exit code -22), com aspas roda limpo.
    """
    raw = str(path).replace("\\", "/")
    escaped = raw.replace(":", r"\:")
    return f"'{escaped}'"


def _ass_filter(ass_path: Path, fonts_dir: Path | None) -> str:
    """Filtro `ass=` com o diretorio de fontes embarcadas, quando ele existe.

    Sem `fontsdir`, o libass procura a fonte do estilo no fontconfig do sistema e, se nao
    achar, cai numa fonte generica EM SILENCIO - o clipe sai com a legenda errada sem
    nada no log. Apontar pra `assets/fonts` faz a fonte versionada no repo valer em
    qualquer maquina e no container.
    """
    parts = [f"ass={_escape_filter_path(ass_path)}"]
    if fonts_dir is not None:
        parts.append(f"fontsdir={_escape_filter_path(Path(fonts_dir))}")
    return ":".join(parts)


def burn_in(
    video_path: str | Path,
    ass_path: str | Path,
    output_path: str | Path,
    crf: int = 20,
    preset: str = "medium",
    video_codec: str = "libx264",
    input_decoder: str | None = None,
    fonts_dir: str | Path | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> None:
    video_path = Path(video_path)
    ass_path = Path(ass_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_fonts_dir = Path(fonts_dir) if fonts_dir is not None else None
    if resolved_fonts_dir is not None and not resolved_fonts_dir.is_dir():
        raise FileNotFoundError(
            f"Diretorio de fontes da legenda nao existe: {resolved_fonts_dir}. "
            "Rode `python scripts/fetch_fonts.py` a partir de engine/."
        )

    cmd = [
        "ffmpeg",
        "-y",
        *hwaccel_decode_flags(input_decoder),
        "-i",
        str(video_path),
        "-vf",
        _ass_filter(ass_path, resolved_fonts_dir),
        *video_encode_flags(video_codec, crf, preset),
        "-c:a",
        "copy",
        str(output_path),
    ]
    runner(cmd, check=True, capture_output=True)
