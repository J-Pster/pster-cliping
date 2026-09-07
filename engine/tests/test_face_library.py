"""Testes da biblioteca de referencia facial: so devolve quem tem foto de verdade salva."""

from __future__ import annotations

from clipador.thumbnail.face_library import PoliticalFigure, available_figures, find_figure


def _figure(tmp_path, slug: str, with_photo: bool) -> PoliticalFigure:
    directory = tmp_path / slug
    directory.mkdir()
    if with_photo:
        (directory / f"{slug}_01.jpg").write_bytes(b"fake jpg")
    return PoliticalFigure(slug=slug, display_name=slug.title(), reference_dir=directory)


def test_available_figures_filtra_quem_nao_tem_foto(tmp_path):
    com_foto = _figure(tmp_path, "com_foto", with_photo=True)
    sem_foto = _figure(tmp_path, "sem_foto", with_photo=False)

    resultado = available_figures((com_foto, sem_foto))

    assert resultado == (com_foto,)


def test_available_figures_pasta_inexistente_e_descartada(tmp_path):
    fantasma = PoliticalFigure("fantasma", "Fantasma", tmp_path / "nao_existe")

    assert available_figures((fantasma,)) == ()


def test_available_figures_ignora_arquivo_nao_imagem(tmp_path):
    directory = tmp_path / "so_texto"
    directory.mkdir()
    (directory / "notas.txt").write_text("nao e foto")
    figure = PoliticalFigure("so_texto", "So Texto", directory)

    assert available_figures((figure,)) == ()


def test_available_figures_lista_vazia_devolve_vazio():
    assert available_figures(()) == ()


def test_find_figure_acha_pelo_slug(tmp_path):
    alvo = _figure(tmp_path, "alvo", with_photo=True)
    outro = _figure(tmp_path, "outro", with_photo=True)

    assert find_figure("alvo", (alvo, outro)) is alvo


def test_find_figure_slug_desconhecido_devolve_none(tmp_path):
    alvo = _figure(tmp_path, "alvo", with_photo=True)

    assert find_figure("nao_cadastrado", (alvo,)) is None
