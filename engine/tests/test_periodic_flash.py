"""Testes de `PeriodicImageFlasher`: montagem do comando ffmpeg e validacao de entrada,
sem ffmpeg real (runner e frame_sampler injetados)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from clipador.export.periodic_flash import PeriodicFlashError, PeriodicImageFlasher


def fake_frame_sampler(width=1080, height=1920):
    return SimpleNamespace(frame_size=lambda video_path: (width, height))


# --- build_command -----------------------------------------------------------


def test_build_command_monta_filter_complex_com_intervalo_e_duracao_default():
    flasher = PeriodicImageFlasher()

    command = flasher.build_command("video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920)

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "between(mod(t\\,10),0,0.3)" in filter_complex
    assert "gte(t,10)" in filter_complex


def test_build_command_usa_intervalo_e_duracao_configurados():
    flasher = PeriodicImageFlasher(interval_seconds=5.0, flash_duration_seconds=0.5)

    command = flasher.build_command("video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920)

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "between(mod(t\\,5),0,0.5)" in filter_complex
    assert "gte(t,5)" in filter_complex


def test_build_command_sem_skip_first_flash_nao_tem_clausula_gte():
    flasher = PeriodicImageFlasher(skip_first_flash=False)

    command = flasher.build_command("video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920)

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "between(mod(t\\,10),0,0.3)'" in filter_complex
    assert "gte(t" not in filter_complex


def test_build_command_normaliza_a_imagem_com_format_e_setsar():
    flasher = PeriodicImageFlasher()

    command = flasher.build_command("video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920)

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "setsar=1,format=yuv420p[img]" in filter_complex


def test_build_command_mapeia_video_de_saida_e_copia_audio_do_input_0():
    flasher = PeriodicImageFlasher()

    command = flasher.build_command("video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920)

    assert "[outv]" in command
    assert command[command.index("-map") + 1] == "[outv]"
    assert "0:a" in command
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[-1] == "out.mp4"


def test_build_command_inputs_video_e_imagem_sem_loop_ou_framerate():
    flasher = PeriodicImageFlasher()

    command = flasher.build_command("video.mp4", "outro.jpg", "out.mp4", width=1080, height=1920)

    assert command[command.index("-i") + 1] == "video.mp4"
    assert "-loop" not in command
    assert "-framerate" not in command


# --- apply -------------------------------------------------------------------


def test_apply_chama_frame_sampler_e_runner_com_o_comando_montado(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    image_path = tmp_path / "outro.jpg"
    image_path.write_bytes(b"image")
    output_path = tmp_path / "out.mp4"

    chamados = {}

    def fake_runner(command, check):
        chamados["command"] = command
        chamados["check"] = check

    flasher = PeriodicImageFlasher(
        frame_sampler=fake_frame_sampler(width=1080, height=1920),
        runner=fake_runner,
    )

    result = flasher.apply(video_path, image_path, output_path)

    assert result == output_path
    assert chamados["check"] is True
    assert chamados["command"][chamados["command"].index("-i") + 1] == str(video_path)
    assert chamados["command"][-1] == str(output_path)


def test_apply_levanta_erro_se_video_nao_existe(tmp_path):
    image_path = tmp_path / "outro.jpg"
    image_path.write_bytes(b"image")

    flasher = PeriodicImageFlasher(
        frame_sampler=fake_frame_sampler(), runner=lambda command, check: None
    )

    with pytest.raises(PeriodicFlashError):
        flasher.apply(tmp_path / "nao_existe.mp4", image_path, tmp_path / "out.mp4")


def test_apply_levanta_erro_se_imagem_nao_existe(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")

    flasher = PeriodicImageFlasher(
        frame_sampler=fake_frame_sampler(), runner=lambda command, check: None
    )

    with pytest.raises(PeriodicFlashError):
        flasher.apply(video_path, tmp_path / "nao_existe.jpg", tmp_path / "out.mp4")
