from pathlib import Path

import pytest

from clipador.kb.knowledge import KnowledgeBase, KnowledgeDocument
from clipador.select.models import (
    LONG_FORMAT,
    LONG_MAX_SECONDS,
    LONG_MIN_SECONDS,
    SHORT_FORMAT,
    SHORT_MIN_SECONDS,
)
from clipador.select.selector import (
    TOOL_NAME,
    build_transcript_view,
    duration_tolerance_window,
    filter_used_ranges,
    select_clips,
    select_clips_for_targets,
    validate_candidates,
)
from clipador.select.silence import expand_to_min_duration, silence_boundaries, snap_to_silence
from clipador.transcribe.models import Segment, TranscriptionResult, Word

# Tres blocos de fala de 4 palavras, separados por pausas de 0.9s.
BLOCK_STARTS = (0.0, 2.5, 5.0)
WORD_DURATION = 0.4


def build_transcription() -> TranscriptionResult:
    segments: list[Segment] = []
    word_id = 0
    for segment_index, block_start in enumerate(BLOCK_STARTS):
        words: list[Word] = []
        for offset in range(4):
            start = block_start + offset * WORD_DURATION
            words.append(
                Word(id=word_id, text=f"p{word_id}", start=start, end=start + WORD_DURATION)
            )
            word_id += 1
        segments.append(
            Segment(
                id=segment_index,
                start=words[0].start,
                end=words[-1].end,
                text=" ".join(w.text for w in words),
                words=words,
                speaker=f"SPEAKER_{segment_index:02d}",
            )
        )
    return TranscriptionResult(segments=segments, language="pt", duration=6.6)


def build_uniform_transcription(word_count: int, word_duration: float = 1.0) -> TranscriptionResult:
    """Transcricao de um so segmento, palavras contiguas (sem pausa), pra controlar
    duracao exata de candidato em segundos: word i cobre [i*word_duration, (i+1)*word_duration)."""
    words = [
        Word(id=i, text=f"w{i}", start=i * word_duration, end=(i + 1) * word_duration)
        for i in range(word_count)
    ]
    segment = Segment(
        id=0,
        start=words[0].start,
        end=words[-1].end,
        text=" ".join(w.text for w in words),
        words=words,
        speaker="SPEAKER_00",
    )
    return TranscriptionResult(segments=[segment], language="pt", duration=words[-1].end)


def build_blocky_transcription(
    block_count: int,
    words_per_block: int = 3,
    word_duration: float = 1.0,
    block_spacing: float = 20.0,
) -> TranscriptionResult:
    """Varios blocos de fala curtos separados por pausas longas (`block_spacing`), pra
    testar expansao de contexto atravessando multiplos boundaries de silencio."""
    segments: list[Segment] = []
    word_id = 0
    for block_index in range(block_count):
        block_start = block_index * block_spacing
        words: list[Word] = []
        for offset in range(words_per_block):
            start = block_start + offset * word_duration
            words.append(
                Word(id=word_id, text=f"b{block_index}w{word_id}", start=start, end=start + word_duration)
            )
            word_id += 1
        segments.append(
            Segment(
                id=block_index,
                start=words[0].start,
                end=words[-1].end,
                text=" ".join(w.text for w in words),
                words=words,
                speaker="SPEAKER_00",
            )
        )
    return TranscriptionResult(segments=segments, language="pt", duration=segments[-1].end)


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


def client_with(candidates: list[dict]) -> FakeClient:
    return FakeClient(
        FakeResponse([FakeTextBlock(), FakeToolUseBlock(TOOL_NAME, {"candidates": candidates})])
    )


class FakeMessagesSequence:
    """Uma resposta por chamada, na ordem dada; repete a ultima se chamado mais vezes
    (mesmo comportamento de `test_pipeline.py`) - usado pra testar rodadas sucessivas
    de `select_clips_for_targets`."""

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


def client_sequence(*candidate_lists: list[dict]) -> FakeClientSequence:
    responses = [
        FakeResponse([FakeToolUseBlock(TOOL_NAME, {"candidates": candidates})])
        for candidates in candidate_lists
    ]
    return FakeClientSequence(FakeMessagesSequence(responses))


def candidate(start: int, end: int, **overrides) -> dict:
    payload = {
        "start_word_id": start,
        "end_word_id": end,
        "format": SHORT_FORMAT,
        "score": 80,
        "justificativa": "Cita a pauta de exemplo: transparencia fiscal.",
    }
    payload.update(overrides)
    return payload


# --- silencio -------------------------------------------------------------


def test_silence_boundaries_detecta_os_tres_blocos():
    starts, ends = silence_boundaries(build_transcription().words)

    assert starts == [0, 4, 8]
    assert ends == [3, 7, 11]


def test_snap_to_silence_move_corte_para_a_pausa_mais_proxima():
    assert snap_to_silence(build_transcription(), 5, 6) == (4, 7)


def test_snap_to_silence_mantem_corte_ja_alinhado():
    assert snap_to_silence(build_transcription(), 4, 7) == (4, 7)


def test_snap_to_silence_desempata_para_o_indice_anterior():
    assert snap_to_silence(build_transcription(), 2, 9) == (0, 7)


def test_snap_to_silence_com_threshold_alto_nao_encontra_pausa():
    assert snap_to_silence(build_transcription(), 5, 6, threshold=10.0) == (0, 11)


def test_snap_to_silence_rejeita_word_id_inexistente():
    with pytest.raises(KeyError):
        snap_to_silence(build_transcription(), 0, 999)


def test_snap_to_silence_rejeita_intervalo_invertido():
    with pytest.raises(ValueError):
        snap_to_silence(build_transcription(), 7, 4)


# --- validacao ------------------------------------------------------------


def test_validate_candidates_descarta_word_id_fora_do_range():
    assert validate_candidates([candidate(0, 999)], build_transcription()) == []


def test_validate_candidates_descarta_intervalo_invertido():
    assert validate_candidates([candidate(7, 4)], build_transcription()) == []


def test_validate_candidates_descarta_formato_desconhecido():
    assert validate_candidates([candidate(0, 3, format="vertical")], build_transcription()) == []


def test_validate_candidates_clampa_score():
    transcription = build_transcription()

    alto = validate_candidates([candidate(0, 3, score=500)], transcription)[0]
    baixo = validate_candidates([candidate(0, 3, score=-10)], transcription)[0]

    assert alto.score == 99
    assert baixo.score == 0


def test_validate_candidates_preenche_timestamps_reais():
    clip = validate_candidates([candidate(4, 7)], build_transcription())[0]

    assert clip.start == pytest.approx(2.5)
    assert clip.end == pytest.approx(4.1)
    assert clip.duration == pytest.approx(1.6)


def test_validate_candidates_sem_snap_preserva_os_ids_do_llm():
    clip = validate_candidates([candidate(5, 6)], build_transcription(), snap=False)[0]

    assert (clip.start_word_id, clip.end_word_id) == (5, 6)


def test_validate_candidates_sem_palavras_retorna_vazio():
    assert validate_candidates([candidate(0, 3)], TranscriptionResult()) == []


# --- expansao de contexto (expand_to_min_duration) -------------------------


def test_expand_to_min_duration_cresce_alternando_pra_tras_e_pra_frente():
    transcription = build_blocky_transcription(block_count=5, words_per_block=3, block_spacing=20.0)
    # bloco do meio (indice 2): word ids 6,7,8 = 40.0s-43.0s
    result = expand_to_min_duration(transcription, 6, 8, min_seconds=50.0, max_seconds=100.0)

    assert result == (3, 14)  # cresceu pro bloco 1 (ids 3-5) e pro bloco 4 (ids 12-14)
    duration = transcription.word_by_id(14).end - transcription.word_by_id(3).start
    assert 50.0 <= duration <= 100.0


def test_expand_to_min_duration_cresce_so_pro_lado_que_tem_bloco():
    transcription = build_blocky_transcription(block_count=5, words_per_block=3, block_spacing=20.0)
    # bloco inicial (indice 0): so tem vizinho pra frente.
    result = expand_to_min_duration(transcription, 0, 2, min_seconds=40.0, max_seconds=200.0)

    assert result[0] == 0  # nao tem pra onde crescer pra tras, fica no inicio


def test_expand_to_min_duration_devolve_none_quando_estoura_o_teto():
    transcription = build_blocky_transcription(block_count=5, words_per_block=3, block_spacing=20.0)

    result = expand_to_min_duration(transcription, 6, 8, min_seconds=200.0, max_seconds=50.0)

    assert result is None


def test_expand_to_min_duration_devolve_none_quando_esgota_a_transcricao():
    transcription = build_blocky_transcription(block_count=3, words_per_block=3, block_spacing=20.0)

    result = expand_to_min_duration(transcription, 3, 5, min_seconds=1000.0, max_seconds=2000.0)

    assert result is None


# --- rede de seguranca de duracao (enforce_duration_bounds) ---------------


def test_enforce_duration_bounds_descarta_long_curto_demais():
    """Reproduz o bug real de producao: LLM rotula um trecho de 90s como long_16x9,
    que exige 5-15min. Com a rede de seguranca ligada, o candidato e descartado em vez
    de virar um clipe 16:9 do tamanho de um curto."""
    transcription = build_uniform_transcription(200)
    curto_demais = candidate(0, 89, format=LONG_FORMAT)  # word 89 termina em 90.0s

    resultado = validate_candidates(
        [curto_demais], transcription, snap=False, enforce_duration_bounds=True
    )

    assert resultado == []


def test_enforce_duration_bounds_aceita_long_dentro_da_janela():
    transcription = build_uniform_transcription(700)
    valido = candidate(0, 599, format=LONG_FORMAT)  # 600s = 10min

    resultado = validate_candidates(
        [valido], transcription, snap=False, enforce_duration_bounds=True
    )

    assert len(resultado) == 1
    assert resultado[0].duration == pytest.approx(600.0)


def test_enforce_duration_bounds_descarta_short_fora_da_janela():
    transcription = build_uniform_transcription(200)
    curto_demais = candidate(0, 9, format=SHORT_FORMAT)  # 10s, bem abaixo de 60s

    resultado = validate_candidates(
        [curto_demais], transcription, snap=False, enforce_duration_bounds=True
    )

    assert resultado == []


def test_enforce_duration_bounds_repara_candidato_curto_demais_puxando_contexto():
    """Caso real que motivou o reparo: LLM propoe um trecho de poucos segundos como
    short_9x16 (exige 60-90s) - em vez de descartar de cara, completa puxando blocos de
    fala vizinhos ate a janela do formato, exatamente como pedido (contexto antes/depois)."""
    transcription = build_blocky_transcription(block_count=10, words_per_block=2, block_spacing=15.0)
    curto_demais = candidate(6, 7, format=SHORT_FORMAT)  # bloco isolado de 2s

    resultado = validate_candidates(
        [curto_demais], transcription, snap=False, enforce_duration_bounds=True
    )

    assert len(resultado) == 1
    clip = resultado[0]
    lower_bound, upper_bound = duration_tolerance_window(SHORT_FORMAT)
    assert lower_bound <= clip.duration <= upper_bound
    assert (clip.start_word_id, clip.end_word_id) != (6, 7)


def test_duration_tolerance_window_formato_longo_tem_piso_rigido():
    """Pedido explicito do usuario: nunca aceitar long_16x9 abaixo de LONG_MIN_SECONDS
    (8min) - diferente do curto, que tem folga pra baixo (LOWER_TOLERANCE_RATIO)."""
    lower_bound, upper_bound = duration_tolerance_window(LONG_FORMAT)

    assert lower_bound == LONG_MIN_SECONDS
    assert upper_bound > LONG_MAX_SECONDS


def test_duration_tolerance_window_formato_curto_mantem_folga_pra_baixo():
    lower_bound, _ = duration_tolerance_window(SHORT_FORMAT)

    assert lower_bound < SHORT_MIN_SECONDS


def test_enforce_duration_bounds_desligado_por_padrao_ignora_duracao():
    """Default (False) preserva o comportamento antigo, usado pelos testes que nao
    testam politica de duracao (fixtures sinteticas minusculas)."""
    transcription = build_uniform_transcription(200)
    curto_demais = candidate(0, 9, format=SHORT_FORMAT)

    resultado = validate_candidates([curto_demais], transcription, snap=False)

    assert len(resultado) == 1


# --- dedup entre rodadas (filter_used_ranges) -------------------------------


def test_filter_used_ranges_descarta_sobreposicao_no_mesmo_formato():
    transcription = build_uniform_transcription(200)
    validated = validate_candidates(
        [candidate(0, 69, format=SHORT_FORMAT)], transcription, snap=False
    )

    resultado = filter_used_ranges(validated, {SHORT_FORMAT: [(0, 69)]})

    assert resultado == []


def test_filter_used_ranges_permite_mesmo_trecho_em_formato_diferente():
    """O mesmo assunto pode virar um clipe curto E um longo - dedup e so dentro do
    mesmo formato."""
    transcription = build_uniform_transcription(200)
    validated = validate_candidates(
        [candidate(0, 69, format=SHORT_FORMAT)], transcription, snap=False
    )

    resultado = filter_used_ranges(validated, {LONG_FORMAT: [(0, 69)]})

    assert len(resultado) == 1


def test_filter_used_ranges_mantem_trecho_sem_sobreposicao():
    transcription = build_uniform_transcription(200)
    validated = validate_candidates(
        [candidate(100, 169, format=SHORT_FORMAT)], transcription, snap=False
    )

    resultado = filter_used_ranges(validated, {SHORT_FORMAT: [(0, 69)]})

    assert len(resultado) == 1


def test_filter_used_ranges_tolerancia_permite_sobreposicao_pequena():
    """Categoria jogos: um pedacinho do fim de um trecho usado pode virar o inicio do
    proximo (ver overlap_tolerance_words em selector.py)."""
    transcription = build_uniform_transcription(200)
    validated = validate_candidates(
        [candidate(65, 134, format=SHORT_FORMAT)], transcription, snap=False
    )

    # Sobreposicao de 5 palavras (65-69) contra o trecho ja usado (0-69).
    resultado = filter_used_ranges(
        validated, {SHORT_FORMAT: [(0, 69)]}, overlap_tolerance_words=10
    )

    assert len(resultado) == 1


def test_filter_used_ranges_tolerancia_ainda_descarta_sobreposicao_grande_demais():
    transcription = build_uniform_transcription(200)
    validated = validate_candidates(
        [candidate(30, 99, format=SHORT_FORMAT)], transcription, snap=False
    )

    # Sobreposicao de 40 palavras (30-69), acima da tolerancia de 10.
    resultado = filter_used_ranges(
        validated, {SHORT_FORMAT: [(0, 69)]}, overlap_tolerance_words=10
    )

    assert resultado == []


# --- meta por formato entre rodadas (select_clips_for_targets) -------------


def test_select_clips_for_targets_acumula_ate_bater_a_meta_ignorando_repetido():
    transcription = build_uniform_transcription(600)
    client = client_sequence(
        [candidate(0, 69, format=SHORT_FORMAT), candidate(100, 169, format=SHORT_FORMAT)],
        # candidato repetido (mesmo intervalo da rodada 1) + um novo - so o novo conta
        [candidate(0, 69, format=SHORT_FORMAT), candidate(200, 269, format=SHORT_FORMAT)],
    )

    # Testa acumulacao/dedup entre rodadas, nao politica de duracao - os intervalos da
    # fixture (70s cada) sao maiores que a janela do formato curto de proposito, pra nao
    # precisar reajustar toda vez que SHORT_MIN/MAX_SECONDS mudar.
    resultado = select_clips_for_targets(
        transcription,
        build_kb(),
        {SHORT_FORMAT: 3},
        client=client,
        snap=False,
        enforce_duration_bounds=False,
    )

    assert [(c.start_word_id, c.end_word_id) for c in resultado[SHORT_FORMAT]] == [
        (0, 69),
        (100, 169),
        (200, 269),
    ]
    assert len(client.messages.calls) == 2  # parou assim que bateu a meta


def test_select_clips_for_targets_exclui_ranges_ja_usados_no_prompt():
    transcription = build_uniform_transcription(300)
    client = client_sequence([candidate(100, 169, format=SHORT_FORMAT)])

    select_clips_for_targets(
        transcription,
        build_kb(),
        {SHORT_FORMAT: 1},
        client=client,
        used_ranges={SHORT_FORMAT: [(0, 69)]},
        snap=False,
    )

    prompt = client.messages.calls[0]["messages"][0]["content"]
    assert "0-69" in prompt
    assert SHORT_FORMAT in prompt


def test_select_clips_for_targets_desiste_apos_rodadas_secas():
    """Se o LLM so devolve trechos ja usados (nenhum novo), desiste em vez de gastar
    `max_attempts` inteiro - video pode nao ter mais material distinto pra oferecer."""
    transcription = build_uniform_transcription(200)
    client = client_sequence([candidate(0, 69, format=SHORT_FORMAT)])  # sempre o mesmo

    resultado = select_clips_for_targets(
        transcription,
        build_kb(),
        {SHORT_FORMAT: 5},
        client=client,
        used_ranges={SHORT_FORMAT: [(0, 69)]},
        snap=False,
        max_attempts=10,
        dry_streak_limit=2,
    )

    assert resultado[SHORT_FORMAT] == []
    assert len(client.messages.calls) == 2  # parou no dry_streak_limit, nao nos 10 attempts


def test_select_clips_for_targets_meta_zero_nao_chama_a_api():
    transcription = build_uniform_transcription(200)
    client = client_sequence([candidate(0, 69, format=SHORT_FORMAT)])

    resultado = select_clips_for_targets(
        transcription, build_kb(), {SHORT_FORMAT: 0}, client=client, snap=False
    )

    assert resultado == {SHORT_FORMAT: []}
    assert len(client.messages.calls) == 0


# --- selecao ponta a ponta (client mockado) -------------------------------


def test_select_clips_retorna_candidatos_validados():
    client = client_with([candidate(5, 6), candidate(9, 10, format=LONG_FORMAT, score=60)])

    clips = select_clips(build_transcription(), build_kb(), client=client)

    assert [(c.start_word_id, c.end_word_id) for c in clips] == [(4, 7), (8, 11)]
    assert [c.format for c in clips] == [SHORT_FORMAT, LONG_FORMAT]


def test_select_clips_forca_a_tool_e_marca_o_cache_do_dossie():
    client = client_with([candidate(4, 7)])

    select_clips(build_transcription(), build_kb(), client=client)
    request = client.messages.calls[0]

    assert request["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert [tool["name"] for tool in request["tools"]] == [TOOL_NAME]
    assert request["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "Pauta de exemplo: transparencia fiscal." in request["system"][-1]["text"]


def test_select_clips_envia_transcricao_com_word_ids():
    client = client_with([candidate(4, 7)])

    select_clips(build_transcription(), build_kb(), client=client)
    prompt = client.messages.calls[0]["messages"][0]["content"]

    assert "[4] p4" in prompt
    assert "ids validos: 0 a 11" in prompt


def test_select_clips_descarta_alucinacao_e_mantem_o_resto():
    client = client_with([candidate(0, 999), candidate(4, 7)])

    clips = select_clips(build_transcription(), build_kb(), client=client)

    assert [(c.start_word_id, c.end_word_id) for c in clips] == [(4, 7)]


def test_select_clips_respeita_max_candidates():
    client = client_with([candidate(0, 3), candidate(4, 7), candidate(8, 11)])

    clips = select_clips(build_transcription(), build_kb(), client=client, max_candidates=2)

    assert len(clips) == 2
    assert client.messages.calls[0]["messages"][0]["content"].endswith(
        f"Aponte no maximo 2 candidatos a clipe, misturando {SHORT_FORMAT} e {LONG_FORMAT} "
        "quando o material permitir."
    )


def test_select_clips_sem_tool_use_na_resposta_retorna_vazio():
    client = FakeClient(FakeResponse([FakeTextBlock()]))

    assert select_clips(build_transcription(), build_kb(), client=client) == []


def test_build_transcript_view_agrupa_por_segmento_com_falante():
    view = build_transcript_view(build_transcription())

    assert "## Segmento 0 | 0.00s-1.60s | fala: SPEAKER_00" in view
    assert "[0] p0 [1] p1 [2] p2 [3] p3" in view


def test_select_clips_diferencia_criterio_curto_de_longo():
    client = client_with([candidate(4, 7)])

    select_clips(build_transcription(), build_kb(), client=client)
    instructions = client.messages.calls[0]["system"][0]["text"]

    assert SHORT_FORMAT in instructions and LONG_FORMAT in instructions
    assert "pronome" in instructions
    assert "payoff" in instructions
    assert "arco" in instructions


def test_kb_do_repositorio_alimenta_o_dossie_do_prompt():
    from clipador.kb.knowledge import load_knowledge_base

    kb = load_knowledge_base(Path(__file__).resolve().parents[1] / "kb" / "politico_pessoa")
    client = client_with([candidate(4, 7)])

    select_clips(build_transcription(), kb, client=client)

    assert "Livro Amarelo" in client.messages.calls[0]["system"][-1]["text"]
