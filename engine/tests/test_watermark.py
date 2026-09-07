"""Testes de `WatermarkImages`/`WatermarkOverlay`: validacao do par de arquivos e
montagem do comando ffmpeg, sem ffmpeg real (runner e frame_sampler injetados)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from clipador.export.watermark import WatermarkError, WatermarkImages, WatermarkOverlay
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT


def fake_frame_sampler(width=1080, height=1920):
    return SimpleNamespace(frame_size=lambda video_path: (width, height))


def build_images(tmp_path) -> WatermarkImages:
    short = tmp_path / "short.png"
    long = tmp_path / "long.png"
    short.write_bytes(b"png curto")
    long.write_bytes(b"png longo")
    return WatermarkImages(short=short, long=long)


# --- WatermarkImages ---------------------------------------------------------


def test_images_recusa_arquivo_curto_inexistente(tmp_path):
    long = tmp_path / "long.png"
    long.write_bytes(b"png longo")

    with pytest.raises(WatermarkError, match="curto"):
        WatermarkImages(short=tmp_path / "nao_existe.png", long=long)


def test_images_recusa_arquivo_longo_inexistente(tmp_path):
    short = tmp_path / "short.png"
    short.write_bytes(b"png curto")

    with pytest.raises(WatermarkError, match="longo"):
        WatermarkImages(short=short, long=tmp_path / "nao_existe.png")


def test_images_escolhe_o_arquivo_do_formato(tmp_path):
    images = build_images(tmp_path)

    assert images.path_for(SHORT_FORMAT) == tmp_path / "short.png"
    assert images.path_for(LONG_FORMAT) == tmp_path / "long.png"


def test_images_recusa_formato_desconhecido(tmp_path):
    images = build_images(tmp_path)

    with pytest.raises(WatermarkError):
        images.path_for("quadrado_1x1")


# --- build_command -----------------------------------------------------------


def test_build_command_escala_a_marca_para_o_tamanho_do_quadro():
    overlay = WatermarkOverlay()

    command = overlay.build_command("video.mp4", "wm.png", "out.mp4", width=1080, height=1920)

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "scale=1080:1920:force_original_aspect_ratio=decrease" in filter_complex


def test_build_command_preenche_a_sobra_com_transparente_e_preserva_alfa():
    overlay = WatermarkOverlay()

    command = overlay.build_command("video.mp4", "wm.png", "out.mp4", width=1920, height=1080)

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "color=0x00000000" in filter_complex
    assert "format=rgba[wm]" in filter_complex


def test_build_command_sobrepoe_no_canto_zero_o_video_inteiro():
    overlay = WatermarkOverlay()

    command = overlay.build_command("video.mp4", "wm.png", "out.mp4", width=1080, height=1920)

    filter_complex = command[command.index("-filter_complex") + 1]
    assert "[0:v][wm]overlay=0:0:format=auto" in filter_complex
    # Sem `enable=`: a marca vale do primeiro ao ultimo frame, ao contrario do flash.
    assert "enable=" not in filter_complex


def test_build_command_mapeia_video_de_saida_e_copia_audio_do_input_0():
    overlay = WatermarkOverlay()

    command = overlay.build_command("video.mp4", "wm.png", "out.mp4", width=1080, height=1920)

    assert command[command.index("-map") + 1] == "[outv]"
    assert "0:a" in command
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[-1] == "out.mp4"


# --- apply -------------------------------------------------------------------


def test_apply_usa_o_tamanho_do_quadro_do_video(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    image_path = tmp_path / "wm.png"
    image_path.write_bytes(b"png")
    chamados = {}

    def fake_runner(command, check):
        chamados["command"] = command
        chamados["check"] = check

    overlay = WatermarkOverlay(
        frame_sampler=fake_frame_sampler(width=1920, height=1080), runner=fake_runner
    )

    result = overlay.apply(video_path, image_path, tmp_path / "out.mp4")

    assert result == tmp_path / "out.mp4"
    assert chamados["check"] is True
    filter_complex = chamados["command"][chamados["command"].index("-filter_complex") + 1]
    assert "scale=1920:1080" in filter_complex


def test_apply_levanta_erro_se_video_nao_existe(tmp_path):
    image_path = tmp_path / "wm.png"
    image_path.write_bytes(b"png")

    overlay = WatermarkOverlay(
        frame_sampler=fake_frame_sampler(), runner=lambda command, check: None
    )

    with pytest.raises(WatermarkError):
        overlay.apply(tmp_path / "nao_existe.mp4", image_path, tmp_path / "out.mp4")


def test_apply_levanta_erro_se_imagem_nao_existe(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")

    overlay = WatermarkOverlay(
        frame_sampler=fake_frame_sampler(), runner=lambda command, check: None
    )

    with pytest.raises(WatermarkError):
        overlay.apply(video_path, tmp_path / "nao_existe.png", tmp_path / "out.mp4")
