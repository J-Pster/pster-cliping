"""Testes do sistema de categoria: garante que as tres categorias existem, que cada modulo
de prompt tem uma variante por categoria, e que a excecao de sobreposicao de jogos e a
proibicao de sobreposicao das demais categorias estao ligadas certo."""

from __future__ import annotations

import pytest

from clipador import category
from clipador.metadata.generator import BASE_INSTRUCTIONS_BY_CATEGORY, build_metadata_tool
from clipador.select.rerank import RERANK_INSTRUCTIONS_BY_CATEGORY
from clipador.select.selector import (
    SELECTION_INSTRUCTIONS_BY_CATEGORY,
    overlap_tolerance_words,
)
from clipador.thumbnail.ai_thumbnail import (
    PROMPT_TEMPLATE_BY_CATEGORY,
    build_thumbnail_generator,
)
from clipador.thumbnail.background import DEFAULT_PROMPT_BY_CATEGORY


def test_categorias_validas():
    assert category.CATEGORIES == (
        category.POLITICS_PERSON,
        category.GAMING,
        category.BOOK_AUDIOBOOK,
    )
    assert category.DEFAULT_CATEGORY == category.POLITICS_PERSON


def test_validate_category_rejeita_categoria_desconhecida():
    with pytest.raises(ValueError):
        category.validate_category("categoria-que-nao-existe")


@pytest.mark.parametrize(
    "registry",
    [
        SELECTION_INSTRUCTIONS_BY_CATEGORY,
        RERANK_INSTRUCTIONS_BY_CATEGORY,
        BASE_INSTRUCTIONS_BY_CATEGORY,
        PROMPT_TEMPLATE_BY_CATEGORY,
        DEFAULT_PROMPT_BY_CATEGORY,
    ],
)
def test_todo_registro_de_prompt_cobre_as_tres_categorias(registry):
    assert set(registry) == set(category.CATEGORIES)
    # cada texto e distinto - nenhuma categoria caiu no mesmo prompt de outra por engano
    assert len(set(registry.values())) == len(registry)


def test_instrucoes_de_selecao_citam_o_dominio_certo():
    politico = SELECTION_INSTRUCTIONS_BY_CATEGORY[category.POLITICS_PERSON]
    jogos = SELECTION_INSTRUCTIONS_BY_CATEGORY[category.GAMING]
    livro = SELECTION_INSTRUCTIONS_BY_CATEGORY[category.BOOK_AUDIOBOOK]

    assert "movimento politico" in politico
    assert "gameplay" in jogos
    assert "highlight" in jogos
    assert "audiobook" in livro
    assert "PROIBIDO qualquer sobreposicao" in livro


def test_overlap_tolerance_so_jogos_permite_sobreposicao():
    assert overlap_tolerance_words(category.POLITICS_PERSON) == 0
    assert overlap_tolerance_words(category.BOOK_AUDIOBOOK) == 0
    assert overlap_tolerance_words(category.GAMING) > 0


def test_metadata_tool_exemplos_de_headline_mudam_por_categoria():
    politico = build_metadata_tool(category.POLITICS_PERSON)
    jogos = build_metadata_tool(category.GAMING)
    livro = build_metadata_tool(category.BOOK_AUDIOBOOK)

    politico_desc = politico["input_schema"]["properties"]["thumbnail_headline"]["description"]
    jogos_desc = jogos["input_schema"]["properties"]["thumbnail_headline"]["description"]
    livro_desc = livro["input_schema"]["properties"]["thumbnail_headline"]["description"]

    assert "FUZIL" in politico_desc
    assert "ELIMINEI O TIME TODO" in jogos_desc
    assert "O INCENTIVO ERRADO MATA" in livro_desc


def test_build_thumbnail_generator_nenhuma_categoria_tem_referencia_facial_fixa():
    """Referencia facial nao e mais default de categoria (era assim que um clipe sobre
    outra pessoa herdava o rosto do apresentador do canal so por a categoria ser
    "politico/pessoa") - agora e sempre uma decisao POR CLIPE, ver
    `thumbnail.subject.select_thumbnail_subject`."""
    politico = build_thumbnail_generator(category.POLITICS_PERSON)
    jogos = build_thumbnail_generator(category.GAMING)
    livro = build_thumbnail_generator(category.BOOK_AUDIOBOOK)

    assert politico.face_reference_dir is None
    assert jogos.face_reference_dir is None
    assert livro.face_reference_dir is None

    assert politico.prompt_template == PROMPT_TEMPLATE_BY_CATEGORY[category.POLITICS_PERSON]
    assert jogos.prompt_template == PROMPT_TEMPLATE_BY_CATEGORY[category.GAMING]
    assert livro.prompt_template == PROMPT_TEMPLATE_BY_CATEGORY[category.BOOK_AUDIOBOOK]


def test_build_thumbnail_generator_rejeita_categoria_invalida():
    with pytest.raises(ValueError):
        build_thumbnail_generator("categoria-que-nao-existe")
