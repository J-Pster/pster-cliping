from pathlib import Path

import pytest

from clipador.kb.knowledge import KnowledgeBase, load_knowledge_base, search_topics

REPO_KB = Path(__file__).resolve().parents[1] / "kb" / "politico_pessoa"


@pytest.fixture
def fake_kb_root(tmp_path: Path) -> Path:
    core = tmp_path / "core"
    core.mkdir()
    (core / "00-voz.md").write_text(
        "# Perfil de voz\n\nFrases curtas e diretas.\n", encoding="utf-8"
    )
    (core / "10-pautas.md").write_text(
        "# Pautas\n\nPauta de exemplo: transparencia fiscal.\n", encoding="utf-8"
    )

    topics = tmp_path / "topics"
    topics.mkdir()
    (topics / "orcamento.md").write_text(
        "# Orcamento\n\n"
        "## Numeros\n\n"
        "linha de contexto anterior\n"
        "A execucao orcamentaria de exemplo ficou parada.\n"
        "linha de contexto posterior\n\n"
        "## Outra secao\n\n"
        "Nada relevante aqui.\n",
        encoding="utf-8",
    )
    (topics / "seguranca.md").write_text(
        "# Seguranca\n\n## Dados\n\nO orcamento da area de exemplo.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_load_knowledge_base_reads_core_in_stable_order(fake_kb_root: Path):
    kb = load_knowledge_base(fake_kb_root, movement="Movimento Exemplo")

    assert kb.movement == "Movimento Exemplo"
    assert [doc.name for doc in kb.core] == ["00-voz", "10-pautas"]
    assert [doc.title for doc in kb.core] == ["Perfil de voz", "Pautas"]


def test_dossier_concatena_core_com_headers(fake_kb_root: Path):
    dossier = load_knowledge_base(fake_kb_root, movement="Movimento Exemplo").dossier()

    assert dossier.startswith("# Dossie: Movimento Exemplo")
    assert "## Perfil de voz" in dossier
    assert "Pauta de exemplo: transparencia fiscal." in dossier


def test_dossier_vazio_quando_nao_ha_core(tmp_path: Path):
    assert load_knowledge_base(tmp_path).dossier() == ""


def test_load_knowledge_base_usa_nome_da_pasta_como_movimento(fake_kb_root: Path):
    assert load_knowledge_base(fake_kb_root).movement == fake_kb_root.name


def test_search_topics_ignora_caixa_e_acento(fake_kb_root: Path):
    kb = load_knowledge_base(fake_kb_root)

    matches = search_topics(kb, "ORÇAMENTÁRIA")

    assert [m.document for m in matches] == ["orcamento"]
    assert matches[0].heading == "Numeros"


def test_search_topics_inclui_linhas_de_contexto(fake_kb_root: Path):
    match = search_topics(load_knowledge_base(fake_kb_root), "orcamentaria")[0]

    assert "linha de contexto anterior" in match.excerpt
    assert "linha de contexto posterior" in match.excerpt


def test_search_topics_exige_todos_os_termos(fake_kb_root: Path):
    kb = load_knowledge_base(fake_kb_root)

    assert search_topics(kb, "orcamento exemplo")
    assert search_topics(kb, "orcamento inexistente") == []


def test_search_topics_respeita_max_results(fake_kb_root: Path):
    kb = load_knowledge_base(fake_kb_root)

    assert len(search_topics(kb, "exemplo")) > 1
    assert len(search_topics(kb, "exemplo", max_results=1)) == 1


def test_search_topics_sem_pasta_de_topicos_retorna_vazio(tmp_path: Path):
    kb = load_knowledge_base(tmp_path)

    assert kb.topics_dir is None
    assert search_topics(kb, "qualquer") == []


def test_search_topics_com_query_vazia_retorna_vazio(fake_kb_root: Path):
    assert search_topics(load_knowledge_base(fake_kb_root), "   ") == []


def test_kb_do_repositorio_carrega_com_conteudo_real():
    kb = load_knowledge_base(REPO_KB, movement="Movimento Exemplo")

    assert isinstance(kb, KnowledgeBase)
    assert len(kb.core) >= 3
    assert not any("PLACEHOLDER" in doc.content for doc in kb.core)
    assert any("Livro Amarelo" in doc.content for doc in kb.core)
    assert search_topics(kb, "fiscal")
