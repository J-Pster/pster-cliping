"""Testes 100% offline de `render_disclaimer_image`: so Pillow, nenhum ffmpeg envolvido.

A fonte embarcada em `assets/fonts` e lida de verdade (mesma convencao de test_subtitles.py).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from clipador.export.eleitoral import render_disclaimer_image

FONTS_DIR = Path("assets/fonts")


def test_render_disclaimer_image_gera_png_rgba_do_tamanho_do_quadro(tmp_path):
    output_path = tmp_path / "eleitoral.png"

    result = render_disclaimer_image(
        "PROPAGANDA ELEITORAL GRATUITA",
        output_path,
        frame_width=1080,
        frame_height=1920,
        fonts_dir=FONTS_DIR,
    )

    assert result == output_path
    assert output_path.is_file()
    with Image.open(output_path) as image:
        assert image.mode == "RGBA"
        assert image.size == (1080, 1920)


def test_render_disclaimer_image_com_texto_desenha_pixels_nao_transparentes(tmp_path):
    output_path = tmp_path / "eleitoral.png"

    render_disclaimer_image(
        "PROPAGANDA ELEITORAL GRATUITA",
        output_path,
        frame_width=1080,
        frame_height=1920,
        fonts_dir=FONTS_DIR,
    )

    with Image.open(output_path) as image:
        alpha = image.getchannel("A")
        assert alpha.getextrema()[1] > 0


def test_render_disclaimer_image_com_texto_vazio_fica_totalmente_transparente(tmp_path):
    output_path = tmp_path / "eleitoral.png"

    render_disclaimer_image(
        "   ",
        output_path,
        frame_width=1080,
        frame_height=1920,
        fonts_dir=FONTS_DIR,
    )

    with Image.open(output_path) as image:
        assert image.mode == "RGBA"
        assert image.size == (1080, 1920)
        alpha = image.getchannel("A")
        assert alpha.getextrema() == (0, 0)


def test_render_disclaimer_image_cria_pasta_de_saida_se_nao_existir(tmp_path):
    output_path = tmp_path / "sub" / "pasta" / "eleitoral.png"

    result = render_disclaimer_image(
        "AVISO",
        output_path,
        frame_width=1080,
        frame_height=1920,
        fonts_dir=FONTS_DIR,
    )

    assert result.is_file()
