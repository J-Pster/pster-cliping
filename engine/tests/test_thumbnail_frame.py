"""Testes de `ThumbnailFramePrepender`: montagem do comando ffmpeg e validacao de
entrada, sem ffmpeg real (runner e frame_sampler injetados)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from clipador.export.thumbnail_frame import (
    ThumbnailFramePrepender,
    ThumbnailFramePrependError,
)


def fake_frame_sampler(width=1080, height=1920, frame_count=300, fps=30.0):
    return SimpleNamespace(
        frame_size=lambda video_path: (width, height),
        frame_count_and_fps=lambda video_path: (frame_count, fps),
    )


# --- build_command -----------------------------------------------------------


def test_build_command_monta_filter_complex_para_3_frames_exatos():
    prepender = ThumbnailFramePrepender()

    command = prepender.build_command(
        "video.mp4", "thumb.png", "out.mp4", width=1080, height=1920, fps=30.0
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "trim=start_frame=0:end_frame=3" in filter_complex
    assert "duration=0.1" in filter_complex  # 3 frames a 30fps = 0.1s de silencio
    assert "concat=n=2:v=1:a=0" in filter_complex
    assert "concat=n=2:v=0:a=1" in filter_complex


def test_build_command_respeita_prepended_frame_count_customizado():
    prepender = ThumbnailFramePrepender(prepended_frame_count=5)

    command = prepender.build_command(
        "video.mp4", "thumb.png", "out.mp4", width=1080, height=1920, fps=30.0
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "trim=start_frame=0:end_frame=5" in filter_complex


def test_build_command_usa_o_fps_do_video_no_input_da_imagem():
    prepender = ThumbnailFramePrepender()

    command = prepender.build_command(
        "video.mp4", "thumb.png", "out.mp4", width=1080, height=1920, fps=30.0
    )

    assert command[command.index("-framerate") + 1] == "30"
    assert command[command.index("-i") + 1] == "thumb.png"


def test_build_command_mapeia_video_e_audio_de_saida():
    prepender = ThumbnailFramePrepender()

    command = prepender.build_command(
        "video.mp4", "thumb.png", "out.mp4", width=1080, height=1920, fps=30.0
    )

    assert "[outv]" in command
    assert "[outa]" in command
    assert command[-1] == "out.mp4"


# --- prepend -------------------------------------------------------------


def test_prepend_chama_frame_sampler_e_runner_com_o_comando_montado(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    thumbnail_path = tmp_path / "thumb.png"
    thumbnail_path.write_bytes(b"thumb")
    output_path = tmp_path / "out.mp4"

    chamados = {}

    def fake_runner(command, check):
        chamados["command"] = command
        chamados["check"] = check

    prepender = ThumbnailFramePrepender(
        frame_sampler=fake_frame_sampler(width=1080, height=1920, fps=30.0),
        runner=fake_runner,
    )

    result = prepender.prepend(video_path, thumbnail_path, output_path)

    assert result == output_path
    assert chamados["check"] is True
    assert chamados["command"][chamados["command"].index("-i") + 1] == str(thumbnail_path)
    assert chamados["command"][-1] == str(output_path)


def test_prepend_levanta_erro_se_video_nao_existe(tmp_path):
    thumbnail_path = tmp_path / "thumb.png"
    thumbnail_path.write_bytes(b"thumb")

    prepender = ThumbnailFramePrepender(
        frame_sampler=fake_frame_sampler(), runner=lambda command, check: None
    )

    with pytest.raises(ThumbnailFramePrependError):
        prepender.prepend(tmp_path / "nao_existe.mp4", thumbnail_path, tmp_path / "out.mp4")


def test_prepend_levanta_erro_se_thumbnail_nao_existe(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")

    prepender = ThumbnailFramePrepender(
        frame_sampler=fake_frame_sampler(), runner=lambda command, check: None
    )

    with pytest.raises(ThumbnailFramePrependError):
        prepender.prepend(video_path, tmp_path / "nao_existe.png", tmp_path / "out.mp4")
