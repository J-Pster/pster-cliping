"""Testes da escolha de assunto visual da thumbnail: so anexa referencia facial de quem
o CONTEUDO do trecho realmente e sobre, nunca um default fixo (ver pipeline.py)."""

from __future__ import annotations

from pathlib import Path

from clipador.select.models import SHORT_FORMAT, ClipCandidate
from clipador.thumbnail.face_library import PoliticalFigure
from clipador.thumbnail.subject import (
    NONE_OPTION,
    TOOL_NAME,
    build_subject_prompt,
    build_subject_tool,
    select_thumbnail_subject,
)


def build_candidate(**overrides) -> ClipCandidate:
    payload = dict(
        start_word_id=0,
        end_word_id=10,
        format=SHORT_FORMAT,
        score=80,
        justificativa="Fala sobre a prisao de um politico.",
        start=0.0,
        end=60.0,
    )
    payload.update(overrides)
    return ClipCandidate(**payload)


RENAN = PoliticalFigure("renan_santos", "Renan Santos", Path("/fake/renan"))
LULA = PoliticalFigure("lula", "Luiz Inácio Lula da Silva", Path("/fake/lula"))
FIGURES = (RENAN, LULA)


class FakeToolUseBlock:
    def __init__(self, name: str, payload: dict):
        self.type = "tool_use"
        self.name = name
        self.input = payload


class FakeResponse:
    def __init__(self, content: list):
        self.content = content


class FakeMessages:
    def __init__(self, response: FakeResponse):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeClient:
    def __init__(self, response: FakeResponse):
        self.messages = FakeMessages(response)


def client_with(subject: str) -> FakeClient:
    return FakeClient(FakeResponse([FakeToolUseBlock(TOOL_NAME, {"subject": subject})]))


# --- build_subject_tool / build_subject_prompt -------------------------------


def test_build_subject_tool_lista_nenhuma_e_todos_os_slugs():
    tool = build_subject_tool(FIGURES)
    options = tool["input_schema"]["properties"]["subject"]["enum"]

    assert options == [NONE_OPTION, "renan_santos", "lula"]
    assert tool["name"] == TOOL_NAME


def test_build_subject_tool_catalogo_cita_nome_de_exibicao():
    tool = build_subject_tool(FIGURES)
    description = tool["input_schema"]["properties"]["subject"]["description"]

    assert "Luiz Inácio Lula da Silva" in description
    assert "Renan Santos" in description


def test_build_subject_prompt_inclui_transcricao_e_justificativa():
    prompt = build_subject_prompt(build_candidate(), "Trecho falando sobre o Lula.")

    assert "Trecho falando sobre o Lula." in prompt
    assert "Fala sobre a prisao de um politico." in prompt


# --- select_thumbnail_subject -------------------------------------------------


def test_select_thumbnail_subject_biblioteca_vazia_nao_chama_a_api():
    client = client_with("lula")

    resultado = select_thumbnail_subject(
        build_candidate(), "trecho qualquer", client=client, figures=()
    )

    assert resultado is None
    assert client.messages.calls == []


def test_select_thumbnail_subject_devolve_a_figura_escolhida():
    client = client_with("lula")

    resultado = select_thumbnail_subject(
        build_candidate(), "trecho sobre o Lula", client=client, figures=FIGURES
    )

    assert resultado is LULA


def test_select_thumbnail_subject_nenhuma_devolve_none():
    client = client_with(NONE_OPTION)

    resultado = select_thumbnail_subject(
        build_candidate(), "trecho generico", client=client, figures=FIGURES
    )

    assert resultado is None


def test_select_thumbnail_subject_forca_a_tool_use():
    client = client_with("renan_santos")

    select_thumbnail_subject(build_candidate(), "trecho", client=client, figures=FIGURES)
    request = client.messages.calls[0]

    assert request["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert [tool["name"] for tool in request["tools"]] == [TOOL_NAME]


def test_select_thumbnail_subject_sem_tool_use_na_resposta_devolve_none():
    client = FakeClient(FakeResponse([]))

    resultado = select_thumbnail_subject(
        build_candidate(), "trecho", client=client, figures=FIGURES
    )

    assert resultado is None


def test_select_thumbnail_subject_slug_desconhecido_devolve_none():
    """Rede de seguranca: mesmo que o `enum` do schema deva impedir isso, um slug fora da
    lista de `figures` disponiveis nunca deve virar uma figura escolhida."""
    client = client_with("nome_que_nao_existe")

    resultado = select_thumbnail_subject(
        build_candidate(), "trecho", client=client, figures=FIGURES
    )

    assert resultado is None
