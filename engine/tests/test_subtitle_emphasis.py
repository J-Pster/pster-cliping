"""Enfase semantica da legenda: a fronteira que valida a resposta do LLM."""

from __future__ import annotations

from types import SimpleNamespace

from clipador.subtitles.emphasis import (
    TOOL_NAME,
    build_emphasis_tool,
    build_user_prompt,
    select_emphasis_word_ids,
)
from clipador.transcribe.models import Word


def _words(count: int, first_id: int = 0) -> list[Word]:
    return [
        Word(id=first_id + i, text=f"palavra{i}", start=i * 0.4, end=i * 0.4 + 0.3)
        for i in range(count)
    ]


class FakeClient:
    def __init__(self, indices):
        self.indices = indices
        self.calls = []

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kwargs):
            self.outer.calls.append(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use", name=TOOL_NAME, input={"indices": self.outer.indices}
                    )
                ]
            )

    @property
    def messages(self):
        return self._Messages(self)


def test_indices_locais_viram_word_ids_globais():
    """O prompt numera as palavras de 0 a N-1 pra economizar token; o resto do pipeline
    so entende `word_id`."""
    words = _words(20, first_id=500)

    resultado = select_emphasis_word_ids(words, client=FakeClient([0, 3]))

    assert resultado == frozenset({500, 503})


def test_indice_fora_da_faixa_e_descartado_com_aviso(caplog):
    with caplog.at_level("WARNING"):
        resultado = select_emphasis_word_ids(_words(10), client=FakeClient([2, 999]))

    assert resultado == frozenset({2})
    assert "fora da faixa" in caplog.text


def test_indice_nao_numerico_e_descartado():
    resultado = select_emphasis_word_ids(_words(10), client=FakeClient([1, "abacaxi", None]))

    assert resultado == frozenset({1})


def test_resposta_sem_tool_use_devolve_conjunto_vazio():
    class SemTool(FakeClient):
        class _Messages:
            def __init__(self, outer):
                self.outer = outer

            def create(self, **kwargs):
                return SimpleNamespace(content=[SimpleNamespace(type="text", text="oi")])

        @property
        def messages(self):
            return self._Messages(self)

    assert select_emphasis_word_ids(_words(10), client=SemTool([])) == frozenset()


def test_orcamento_limita_quantas_palavras_sao_destacadas():
    """Uma a cada ~9 mantem o efeito de ponto de fixacao: se tudo e colorido, nada e."""
    words = _words(18)

    resultado = select_emphasis_word_ids(words, client=FakeClient(list(range(18))))

    assert len(resultado) == 2


def test_trecho_curto_ainda_permite_uma_palavra():
    resultado = select_emphasis_word_ids(_words(3), client=FakeClient([0, 1, 2]))

    assert len(resultado) == 1


def test_lista_vazia_de_palavras_nao_chama_o_llm():
    client = FakeClient([0])

    assert select_emphasis_word_ids([], client=client) == frozenset()
    assert client.calls == []


def test_prompt_numera_cada_palavra():
    prompt = build_user_prompt(_words(3), 1)

    assert "[0]palavra0" in prompt
    assert "[2]palavra2" in prompt


def test_tool_declara_o_teto_de_itens():
    schema = build_emphasis_tool(4)

    assert schema["name"] == TOOL_NAME
    assert schema["input_schema"]["properties"]["indices"]["maxItems"] == 4


def test_chamada_forca_o_uso_da_tool():
    client = FakeClient([0])

    select_emphasis_word_ids(_words(5), client=client)

    assert client.calls[0]["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
