"""Testes de `OutroImageAppender`: montagem do comando ffmpeg e validacao de entrada,
sem ffmpeg real (runner e frame_sampler injetados)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from clipador.export.outro_appender import OutroAppendError, OutroImageAppender


def fake_frame_sampler(width=1080, height=1920, frame_count=300, fps=30.0):
    return SimpleNamespace(
        frame_size=lambda video_path: (width, height),
        frame_count_and_fps=lambda video_path: (frame_count, fps),
    )


# --- build_command -----------------------------------------------------------


def test_build_command_monta_filter_complex_para_a_duracao_default():
    appender = OutroImageAppender()

    command = appender.build_command(
        "video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920, fps=30.0
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "trim=duration=5" in filter_complex
    assert "concat=n=2:v=1:a=0" in filter_complex
    assert "concat=n=2:v=0:a=1" in filter_complex


def test_build_command_usa_duracao_configurada():
    appender = OutroImageAppender(duration_seconds=3.5)

    command = appender.build_command(
        "video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920, fps=30.0
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "trim=duration=3.5" in filter_complex
    assert "duration=3.5[silence]" in filter_complex


def test_build_command_video_antes_da_imagem_nos_inputs_e_no_concat():
    appender = OutroImageAppender()

    command = appender.build_command(
        "video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920, fps=30.0
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "[vid][img]concat=n=2:v=1:a=0[outv]" in filter_complex
    # video (input 0) vem antes da imagem (input 1) na lista de -i.
    assert command[command.index("-i") + 1] == "video.mp4"
    assert command[command.index("-framerate") + 1] == "30"
    assert command[command.index("-loop") + 1] == "1"


def test_build_command_setsar_nos_dois_branches():
    appender = OutroImageAppender()

    command = appender.build_command(
        "video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920, fps=30.0
    )

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "[0:v]format=yuv420p,setsar=1[vid]" in filter_complex
    assert "setsar=1,fps=30" in filter_complex


def test_build_command_mapeia_video_e_audio_de_saida():
    appender = OutroImageAppender()

    command = appender.build_command(
        "video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920, fps=30.0
    )

    assert "[outv]" in command
    assert "[outa]" in command
    assert command[-1] == "out.mp4"


# --- append ----------------------------------------------------------------


def test_append_chama_frame_sampler_e_runner_com_o_comando_montado(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    image_path = tmp_path / "outro.jpg"
    image_path.write_bytes(b"image")
    output_path = tmp_path / "out.mp4"

    chamados = {}

    def fake_runner(command, check):
        chamados["command"] = command
        chamados["check"] = check

    appender = OutroImageAppender(
        frame_sampler=fake_frame_sampler(width=1080, height=1920, fps=30.0),
        runner=fake_runner,
    )

    result = appender.append(video_path, image_path, output_path)

    assert result == output_path
    assert chamados["check"] is True
    assert chamados["command"][chamados["command"].index("-i") + 1] == str(video_path)
    assert chamados["command"][-1] == str(output_path)


def test_append_levanta_erro_se_video_nao_existe(tmp_path):
    image_path = tmp_path / "outro.jpg"
    image_path.write_bytes(b"image")

    appender = OutroImageAppender(
        frame_sampler=fake_frame_sampler(), runner=lambda command, check: None
    )

    with pytest.raises(OutroAppendError):
        appender.append(tmp_path / "nao_existe.mp4", image_path, tmp_path / "out.mp4")


def test_append_levanta_erro_se_imagem_nao_existe(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")

    appender = OutroImageAppender(
        frame_sampler=fake_frame_sampler(), runner=lambda command, check: None
    )

    with pytest.raises(OutroAppendError):
        appender.append(video_path, tmp_path / "nao_existe.jpg", tmp_path / "out.mp4")
