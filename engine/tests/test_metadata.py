import logging
from pathlib import Path

from clipador import category as category_module
from clipador.kb.knowledge import KnowledgeBase, KnowledgeDocument, load_knowledge_base
from clipador.metadata.generator import (
    HEADLINE_REPAIR_TOOL_NAME,
    MAX_HASHTAGS,
    METADATA_TOOL,
    TOOL_NAME,
    _extract_keywords,
    _relevant_topic_matches,
    build_headline_repair_tool,
    build_metadata_tool,
    build_system_blocks,
    build_user_prompt,
    generate_metadata,
    sanitize_hashtags,
    sanitize_headline,
)
from clipador.metadata.models import ClipMetadata
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT, ClipCandidate


def build_kb() -> KnowledgeBase:
    return KnowledgeBase(
        movement="Movimento Exemplo",
        core=[
            KnowledgeDocument(
                name="pautas", title="Pautas", content="Pauta de exemplo: transparencia fiscal."
            )
        ],
        topics_dir=None,
    )


def build_candidate(**overrides) -> ClipCandidate:
    payload = dict(
        start_word_id=4,
        end_word_id=20,
        format=SHORT_FORMAT,
        score=85,
        justificativa="Gancho forte sobre transparencia fiscal.",
        start=2.0,
        end=10.5,
    )
    payload.update(overrides)
    return ClipCandidate(**payload)


class FakeToolUseBlock:
    def __init__(self, name: str, payload: dict):
        self.type = "tool_use"
        self.name = name
        self.input = payload


class FakeTextBlock:
    type = "text"
    text = "texto qualquer"


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


def client_with(payload: dict) -> FakeClient:
    return FakeClient(FakeResponse([FakeTextBlock(), FakeToolUseBlock(TOOL_NAME, payload)]))


class FakeMessagesSequence:
    """Uma resposta por chamada, na ordem dada - usado pra testar o reparo da headline
    (1a chamada usa a tool principal, 2a chamada usa a tool de reparo)."""

    def __init__(self, responses: list[FakeResponse]):
        self._responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[index]


class FakeClientSequence:
    def __init__(self, messages: FakeMessagesSequence):
        self.messages = messages


def client_sequence(*responses: tuple[str, dict]) -> FakeClientSequence:
    """Cada item e (tool_name, payload) da resposta daquela chamada, na ordem."""
    return FakeClientSequence(
        FakeMessagesSequence(
            [FakeResponse([FakeToolUseBlock(name, payload)]) for name, payload in responses]
        )
    )


def metadata_payload(**overrides) -> dict:
    payload = {
        "title": "Renan Santos expõe a farra fiscal",
        "description": "Trecho onde Renan Santos fala sobre transparencia fiscal.",
        "hashtags": ["politica", "transparenciafiscal", "shorts"],
        "kb_references": ["Pauta de exemplo: transparencia fiscal."],
        "thumbnail_headline": "E agora?",
    }
    payload.update(overrides)
    return payload


# --- prompt builders --------------------------------------------------------


def test_build_system_blocks_curto_menciona_gancho_sem_pedir_marcador_de_alcance():
    """O prompt do curto pedia `#shorts` explicitamente. Marcador generico nao diz nada
    sobre o conteudo e ainda gasta uma das 5 vagas de tema."""
    blocks = build_system_blocks(build_kb(), SHORT_FORMAT)
    texts = "\n".join(b["text"] for b in blocks)

    assert "gancho" in texts.lower()
    assert "#shorts" not in texts.lower()


def test_build_system_blocks_longo_menciona_descricao_completa_sem_shorts():
    blocks = build_system_blocks(build_kb(), LONG_FORMAT)
    texts = "\n".join(b["text"] for b in blocks)

    assert "descrição mais completa" in texts.lower() or "descricao mais completa" in texts.lower()
    assert "#shorts" not in texts.lower()


def test_build_system_blocks_varia_entre_formatos():
    short_texts = [b["text"] for b in build_system_blocks(build_kb(), SHORT_FORMAT)]
    long_texts = [b["text"] for b in build_system_blocks(build_kb(), LONG_FORMAT)]

    assert short_texts != long_texts


def test_build_system_blocks_mantem_dossie_no_prefixo_estavel_com_cache():
    short_blocks = build_system_blocks(build_kb(), SHORT_FORMAT)
    long_blocks = build_system_blocks(build_kb(), LONG_FORMAT)

    # instrucao base + dossie sao identicos e vem antes da instrucao de formato.
    assert short_blocks[0] == long_blocks[0]
    assert short_blocks[1] == long_blocks[1]
    assert short_blocks[1]["cache_control"] == {"type": "ephemeral"}
    assert "Pauta de exemplo: transparencia fiscal." in short_blocks[1]["text"]


def test_build_user_prompt_inclui_trecho_e_justificativa():
    prompt = build_user_prompt(build_candidate(), "Renan: precisamos falar de transparencia.")

    assert "Renan: precisamos falar de transparencia." in prompt
    assert "Gancho forte sobre transparencia fiscal." in prompt
    assert SHORT_FORMAT in prompt


def test_build_user_prompt_sem_topic_matches_e_identico_ao_comportamento_anterior():
    sem_matches = build_user_prompt(build_candidate(), "trecho qualquer")
    com_lista_vazia = build_user_prompt(build_candidate(), "trecho qualquer", [])

    assert sem_matches == com_lista_vazia
    assert "kb/topics/" not in sem_matches


def test_build_user_prompt_com_topic_matches_inclui_documento_heading_e_excerto():
    from clipador.kb.knowledge import TopicMatch

    matches = [
        TopicMatch(document="01-tema-fake", heading="Numeros", excerpt="dado relevante aqui", score=2)
    ]

    prompt = build_user_prompt(build_candidate(), "trecho qualquer", matches)

    assert "kb/topics/" in prompt
    assert "01-tema-fake" in prompt
    assert "Numeros" in prompt
    assert "dado relevante aqui" in prompt


# --- extracao de palavras-chave e busca na camada 2 (kb/topics) -------------


def test_extract_keywords_filtra_por_tamanho_minimo():
    keywords = _extract_keywords("o governo fez um ato ontem")

    assert "governo" in keywords
    assert "o" not in keywords
    assert "um" not in keywords
    assert "ato" not in keywords  # 3 letras, abaixo do minimo de 5


def test_extract_keywords_remove_duplicata_e_normaliza_case():
    keywords = _extract_keywords("Fiscal fiscal FISCAL despesa despesa")

    assert keywords.count("fiscal") == 1
    assert keywords.count("despesa") == 1


def test_extract_keywords_remove_pontuacao_nas_bordas():
    keywords = _extract_keywords("fiscal, seguranca! (educacao) 'saude'")

    assert "fiscal" in keywords
    assert "seguranca" in keywords
    assert "educacao" in keywords
    assert "saude" in keywords


def _build_kb_com_topicos(tmp_path) -> KnowledgeBase:
    topics_dir = tmp_path / "topics"
    topics_dir.mkdir()
    (topics_dir / "01-tema-a.md").write_text(
        "# Tema A\n\n## Numeros\n\nOrcamento discutido em detalhe.\n\n## Historico\n\n"
        "Orcamento antigo era diferente.\n",
        encoding="utf-8",
    )
    (topics_dir / "02-tema-b.md").write_text(
        "# Tema B\n\n## Contexto\n\nOrcamento e planejamento juntos.\n",
        encoding="utf-8",
    )
    (topics_dir / "03-tema-c.md").write_text(
        "# Tema C\n\n## Detalhes\n\nPlanejamento estrategico de longo prazo.\n",
        encoding="utf-8",
    )
    return KnowledgeBase(movement="Teste", core=[], topics_dir=topics_dir)


def test_relevant_topic_matches_agrega_matches_de_multiplas_palavras(tmp_path):
    kb = _build_kb_com_topicos(tmp_path)

    matches = _relevant_topic_matches(kb, "queremos falar de orcamento e planejamento")

    documentos = {m.document for m in matches}
    assert "01-tema-a" in documentos or "02-tema-b" in documentos or "03-tema-c" in documentos
    assert len(matches) > 0


def test_relevant_topic_matches_deduplica_por_documento_e_heading_mantendo_maior_score(tmp_path):
    kb = _build_kb_com_topicos(tmp_path)

    matches = _relevant_topic_matches(kb, "orcamento")

    chaves = [(m.document, m.heading) for m in matches]
    assert len(chaves) == len(set(chaves))


def test_relevant_topic_matches_respeita_max_topic_matches(tmp_path):
    kb = _build_kb_com_topicos(tmp_path)

    matches = _relevant_topic_matches(kb, "orcamento planejamento estrategico historico")

    assert len(matches) <= 3


def test_relevant_topic_matches_sem_keywords_retorna_vazio(tmp_path):
    kb = _build_kb_com_topicos(tmp_path)

    assert _relevant_topic_matches(kb, "e a de o um") == []


# --- generate_metadata (client mockado) -------------------------------------


def test_generate_metadata_faz_parsing_da_resposta_estruturada():
    client = client_with(metadata_payload())

    result = generate_metadata(
        build_candidate(), "trecho da transcricao", build_kb(), client=client
    )

    assert result == ClipMetadata(
        title="Renan Santos expõe a farra fiscal",
        description="Trecho onde Renan Santos fala sobre transparencia fiscal.",
        # "shorts" veio na resposta do LLM e foi descartada por `sanitize_hashtags`.
        hashtags=["politica", "transparenciafiscal"],
        format=SHORT_FORMAT,
        kb_references=["Pauta de exemplo: transparencia fiscal."],
        thumbnail_headline="E agora?",
    )


def test_generate_metadata_forca_a_tool_use():
    client = client_with(metadata_payload())

    generate_metadata(build_candidate(), "trecho", build_kb(), client=client)
    request = client.messages.calls[0]

    assert request["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert [tool["name"] for tool in request["tools"]] == [TOOL_NAME]


def test_generate_metadata_usa_instrucao_do_formato_do_candidato():
    client = client_with(metadata_payload())

    generate_metadata(
        build_candidate(format=LONG_FORMAT), "trecho", build_kb(), client=client
    )
    system_blocks = client.messages.calls[0]["system"]

    assert "#shorts" not in system_blocks[-1]["text"].lower()


def test_generate_metadata_usa_a_kb_real_do_repo_e_inclui_matches_de_topico():
    """Teste de integracao leve: confirma que o wiring de generate_metadata ->
    _relevant_topic_matches -> build_user_prompt chega ate o prompt enviado ao client,
    usando a KB real do repo (kb/core + kb/topics ja povoados)."""
    kb_root = Path(__file__).resolve().parents[1] / "kb" / "politico_pessoa"
    kb = load_knowledge_base(kb_root)

    client = client_with(metadata_payload())
    excerto = "o governo brasileiro precisa fazer um ajuste fiscal urgente na divida publica"

    generate_metadata(build_candidate(), excerto, kb, client=client)
    request = client.messages.calls[0]
    prompt = request["messages"][0]["content"]

    assert "kb/topics/" in prompt
    assert "01-ajuste-fiscal" in prompt


def test_generate_metadata_kb_references_vazio_nao_e_erro_e_loga_aviso(caplog):
    client = client_with(metadata_payload(kb_references=[]))

    with caplog.at_level(logging.WARNING):
        result = generate_metadata(build_candidate(), "trecho", build_kb(), client=client)

    assert result.kb_references == []
    assert result.title == "Renan Santos expõe a farra fiscal"
    assert any("kb_references" in record.message for record in caplog.records)


def test_generate_metadata_sem_tool_use_na_resposta_retorna_metadata_vazio():
    client = FakeClient(FakeResponse([FakeTextBlock()]))

    result = generate_metadata(build_candidate(), "trecho", build_kb(), client=client)

    assert result.title == ""
    assert result.hashtags == []
    assert result.kb_references == []
    assert result.thumbnail_headline == ""


# --- headline da thumbnail ---------------------------------------------------


def test_metadata_tool_exige_thumbnail_headline_e_proibe_citar_a_fala():
    schema = METADATA_TOOL["input_schema"]
    headline = schema["properties"]["thumbnail_headline"]

    assert "thumbnail_headline" in schema["required"]
    assert "PROIBIDO" in headline["description"]
    assert "parafrasear" in headline["description"]


def test_base_instructions_reforca_que_a_headline_nao_e_a_fala_do_trecho():
    texts = "\n".join(block["text"] for block in build_system_blocks(build_kb(), SHORT_FORMAT))

    assert "thumbnail_headline" in texts
    assert "legenda queimada" in texts


def test_generate_metadata_propaga_a_headline_da_thumbnail():
    client = client_with(metadata_payload(thumbnail_headline="Virou o jogo"))

    result = generate_metadata(build_candidate(), "trecho", build_kb(), client=client)

    assert result.thumbnail_headline == "Virou o jogo"
    assert result.to_dict()["thumbnail_headline"] == "Virou o jogo"


# --- sanitize_headline (rede de seguranca contra o LLM ignorar o limite) -----


def test_sanitize_headline_descarta_quando_passa_do_maximo_de_palavras():
    """Antes cortava mecanicamente pras primeiras 4 palavras, o que produzia fragmento
    sem sentido (o bug real: 'MULTA QUE ACABA COM' cortado de uma frase maior). Agora
    descarta a headline inteira - reparar via LLM e responsabilidade de generate_metadata,
    nao de sanitize_headline."""
    resultado = sanitize_headline(
        "os dez indicadores da prefeitura ideal segundo especialistas", "transcricao qualquer"
    )

    assert resultado == ""


def test_sanitize_headline_aceita_exatamente_4_palavras_sem_cortar():
    resultado = sanitize_headline("os dez indicadores da", "transcricao qualquer")

    assert resultado == "os dez indicadores da"


def test_sanitize_headline_descarta_quando_e_quase_igual_a_transcricao():
    transcricao = "acho que a tutela precisa ser antecipada nesse caso"

    resultado = sanitize_headline("a tutela precisa ser antecipada", transcricao)

    assert resultado == ""


def test_sanitize_headline_mantem_gancho_curto_sem_relacao_literal_com_a_fala():
    transcricao = "acho que a tutela precisa ser antecipada nesse caso"

    resultado = sanitize_headline("ele perdeu a calma", transcricao)

    assert resultado == "ele perdeu a calma"


def test_sanitize_headline_vazia_devolve_vazia():
    assert sanitize_headline("", "qualquer transcricao") == ""
    assert sanitize_headline("   ", "qualquer transcricao") == ""


def test_generate_metadata_aplica_sanitize_na_headline_da_resposta(caplog):
    transcricao = "a tutela precisa ser antecipada urgentemente"
    client = client_with(metadata_payload(thumbnail_headline="a tutela precisa ser antecipada"))

    with caplog.at_level(logging.WARNING):
        result = generate_metadata(build_candidate(), transcricao, build_kb(), client=client)

    assert result.thumbnail_headline == ""
    assert any("thumbnail_headline" in record.message for record in caplog.records)


# --- reparo da headline via LLM (segunda chamada quando a 1a e rejeitada) ---


def test_generate_metadata_headline_valida_de_primeira_nao_pede_reparo():
    client = client_with(metadata_payload(thumbnail_headline="Virou o jogo"))

    result = generate_metadata(build_candidate(), "trecho", build_kb(), client=client)

    assert result.thumbnail_headline == "Virou o jogo"
    assert len(client.messages.calls) == 1


def test_generate_metadata_repara_headline_comprida_demais_com_segunda_chamada():
    client = client_sequence(
        (TOOL_NAME, metadata_payload(thumbnail_headline="multa que acaba com o traficante")),
        (HEADLINE_REPAIR_TOOL_NAME, {"thumbnail_headline": "multa acaba com trafico"}),
    )

    result = generate_metadata(build_candidate(), "trecho qualquer", build_kb(), client=client)

    assert result.thumbnail_headline == "multa acaba com trafico"
    assert len(client.messages.calls) == 2
    repair_call = client.messages.calls[1]
    assert repair_call["tool_choice"] == {"type": "tool", "name": HEADLINE_REPAIR_TOOL_NAME}
    assert "multa que acaba com o traficante" in repair_call["messages"][0]["content"]
    assert "o maximo e 4" in repair_call["messages"][0]["content"]


def test_generate_metadata_repara_headline_quase_literal_com_segunda_chamada():
    transcricao = "acho que a tutela precisa ser antecipada urgentemente"
    client = client_sequence(
        (TOOL_NAME, metadata_payload(thumbnail_headline="tutela precisa ser antecipada")),
        (HEADLINE_REPAIR_TOOL_NAME, {"thumbnail_headline": "tutela em debate"}),
    )

    result = generate_metadata(build_candidate(), transcricao, build_kb(), client=client)

    assert result.thumbnail_headline == "tutela em debate"
    assert len(client.messages.calls) == 2
    assert "citacao literal" in client.messages.calls[1]["messages"][0]["content"]


def test_generate_metadata_segunda_tentativa_de_reparo_tambem_falha_terceira_acerta():
    """MAX_HEADLINE_REPAIR_ATTEMPTS=2: a primeira geracao falha, o 1o reparo falha de
    novo, o 2o reparo (3a chamada no total) finalmente acerta - o loop nao desiste na
    primeira tentativa de reparo."""
    client = client_sequence(
        (TOOL_NAME, metadata_payload(thumbnail_headline="isso aqui tem palavras demais pra caber")),
        (HEADLINE_REPAIR_TOOL_NAME, {"thumbnail_headline": "ainda com muitas palavras aqui"}),
        (HEADLINE_REPAIR_TOOL_NAME, {"thumbnail_headline": "gancho curto"}),
    )

    result = generate_metadata(build_candidate(), "trecho qualquer", build_kb(), client=client)

    assert result.thumbnail_headline == "gancho curto"
    assert len(client.messages.calls) == 3


def test_generate_metadata_esgota_tentativas_de_reparo_fica_sem_headline(caplog):
    client = client_sequence(
        (TOOL_NAME, metadata_payload(thumbnail_headline="isso aqui tem palavras demais pra caber")),
        (HEADLINE_REPAIR_TOOL_NAME, {"thumbnail_headline": "ainda com muitas palavras aqui"}),
        (HEADLINE_REPAIR_TOOL_NAME, {"thumbnail_headline": "continua com palavras demais aqui"}),
    )

    with caplog.at_level(logging.WARNING):
        result = generate_metadata(build_candidate(), "trecho qualquer", build_kb(), client=client)

    assert result.thumbnail_headline == ""
    # 1 tentativa original + MAX_HEADLINE_REPAIR_ATTEMPTS(2) reparos, nunca mais que isso.
    assert len(client.messages.calls) == 3
    assert any("sem versao valida apos reparo" in record.message for record in caplog.records)


def test_build_headline_repair_tool_usa_o_mesmo_schema_da_tool_principal():
    for category in category_module.CATEGORIES:
        metadata_field = build_metadata_tool(category)["input_schema"]["properties"][
            "thumbnail_headline"
        ]
        repair_field = build_headline_repair_tool(category)["input_schema"]["properties"][
            "thumbnail_headline"
        ]
        assert metadata_field == repair_field


def test_sanitize_hashtags_descarta_marcadores_genericos():
    """Marcador de alcance nao diz nada sobre o conteudo, e a plataforma ja sabe o formato
    pelo proprio upload."""
    assert sanitize_hashtags(["shorts", "Politica", "viral", "fyp", "PCC"]) == [
        "Politica",
        "PCC",
    ]


def test_sanitize_hashtags_corta_no_teto_preservando_a_ordem():
    tags = sanitize_hashtags([f"tema{i}" for i in range(12)])

    assert len(tags) == MAX_HASHTAGS
    assert tags == ["tema0", "tema1", "tema2", "tema3", "tema4"]


def test_sanitize_hashtags_remove_cerquilha_e_duplicata_sem_diferenciar_caixa():
    assert sanitize_hashtags(["#PCC", "pcc", " Faccoes ", ""]) == ["PCC", "Faccoes"]


def test_tool_schema_nao_usa_maxitems():
    """Regressao de um erro que so aparece contra a API real, nunca offline.

    Colocar `maxItems` no array de hashtags fez a Anthropic recusar a requisicao INTEIRA:
    `tools.0.custom: For 'array' type, property 'maxItems' is not supported`. O efeito no
    pipeline foi todo clipe falhar na etapa de metadados. O teto de hashtags pertence a
    descricao (pedido ao modelo) e a `sanitize_hashtags` (garantia na volta), nunca ao
    schema.
    """

    def keywords(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keywords(value)
        elif isinstance(node, list):
            for item in node:
                yield from keywords(item)

    for category in category_module.CATEGORIES:
        schema = build_metadata_tool(category)["input_schema"]
        assert "maxItems" not in set(keywords(schema))


def test_sanitize_hashtags_remove_espaco_interno():
    """Hashtag com espaco quebra ao publicar: `#seguranca publica` vira a tag
    `#seguranca` mais a palavra solta "publica", e o termo que importava se perde."""
    assert sanitize_hashtags(["seguranca publica", "crime organizado"]) == [
        "segurancapublica",
        "crimeorganizado",
    ]


def test_sanitize_hashtags_preserva_acento_e_underscore():
    assert sanitize_hashtags(["tráfico", "sistema_prisional"]) == [
        "tráfico",
        "sistema_prisional",
    ]


def test_sanitize_hashtags_descarta_tag_que_fica_vazia_apos_limpeza():
    assert sanitize_hashtags(["!!!", "---", "ok"]) == ["ok"]
