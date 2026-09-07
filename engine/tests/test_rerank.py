import pytest

from clipador.kb.knowledge import KnowledgeBase, KnowledgeDocument
from clipador.select.models import LONG_FORMAT, SHORT_FORMAT, ClipCandidate
from clipador.select.rerank import (
    RERANK_TOOL_NAME,
    build_rerank_prompt,
    rerank_candidates,
)
from clipador.select.selector import TOOL_NAME, select_clips
from clipador.transcribe.models import Segment, TranscriptionResult, Word

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


def clip(start_id: int, end_id: int, score: int = 50, **overrides) -> ClipCandidate:
    transcription = build_transcription()
    payload = {
        "start_word_id": start_id,
        "end_word_id": end_id,
        "format": SHORT_FORMAT,
        "score": score,
        "justificativa": f"primeira passagem {start_id}",
        "start": transcription.word_by_id(start_id).start,
        "end": transcription.word_by_id(end_id).end,
    }
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
    def __init__(self, responses: list[FakeResponse]):
        self._responses = responses
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]


class FakeClient:
    def __init__(self, *responses: FakeResponse):
        self.messages = FakeMessages(list(responses))


def rerank_client(ranking: list[dict]) -> FakeClient:
    return FakeClient(
        FakeResponse([FakeTextBlock(), FakeToolUseBlock(RERANK_TOOL_NAME, {"ranking": ranking})])
    )


def entry(index: int, score: int, justificativa: str = "gancho forte") -> dict:
    return {"index": index, "score": score, "justificativa": justificativa}


# --- reordenacao ----------------------------------------------------------


def test_rerank_reordena_e_reescreve_o_score_pela_resposta():
    candidates = [clip(0, 3, score=10), clip(4, 7, score=20), clip(8, 11, score=30)]
    # Sem embaralhamento: seed que preserva a ordem nao existe garantidamente, entao
    # descobrimos a ordem enviada pelo prompt e ranqueamos o ultimo item primeiro.
    client = rerank_client([entry(2, 90), entry(0, 40), entry(1, 15)])

    ranked = rerank_candidates(candidates, build_transcription(), build_kb(), client=client, seed=7)
    sent = _sent_start_ids(client)

    assert [c.start_word_id for c in ranked] == [sent[2], sent[0], sent[1]]
    assert [c.score for c in ranked] == [90, 40, 15]


def test_rerank_substitui_a_justificativa_pelo_veredito_do_juiz():
    client = rerank_client([entry(0, 88, "fecha a ideia e cita a pauta fiscal")])

    ranked = rerank_candidates([clip(0, 3)], build_transcription(), build_kb(), client=client)

    assert ranked[0].justificativa == "fecha a ideia e cita a pauta fiscal"


def test_rerank_nao_muta_os_candidatos_de_entrada():
    original = clip(0, 3, score=10)
    client = rerank_client([entry(0, 99)])

    rerank_candidates([original], build_transcription(), build_kb(), client=client)

    assert original.score == 10
    assert original.justificativa == "primeira passagem 0"


def test_rerank_preserva_o_resto_do_candidato():
    client = rerank_client([entry(0, 70)])

    ranked = rerank_candidates(
        [clip(4, 7, format=LONG_FORMAT)], build_transcription(), build_kb(), client=client
    )

    assert (ranked[0].start_word_id, ranked[0].end_word_id) == (4, 7)
    assert ranked[0].format == LONG_FORMAT
    assert ranked[0].start == pytest.approx(2.5)
    assert ranked[0].end == pytest.approx(4.1)


# --- robustez da resposta -------------------------------------------------


def test_rerank_manda_para_o_fim_o_candidato_que_o_juiz_esqueceu():
    candidates = [clip(0, 3), clip(4, 7), clip(8, 11)]
    client = rerank_client([entry(1, 90)])

    ranked = rerank_candidates(candidates, build_transcription(), build_kb(), client=client, seed=3)
    sent = _sent_start_ids(client)

    assert len(ranked) == 3
    assert ranked[0].start_word_id == sent[1]
    assert ranked[0].score == 90
    assert {c.start_word_id for c in ranked[1:]} == {sent[0], sent[2]}
    assert [c.score for c in ranked[1:]] == [50, 50]


def test_rerank_ignora_indice_fora_do_range_e_repetido():
    candidates = [clip(0, 3), clip(4, 7)]
    client = rerank_client([entry(1, 90), entry(99, 80), entry(1, 10), entry(0, 20)])

    ranked = rerank_candidates(candidates, build_transcription(), build_kb(), client=client, seed=1)

    assert [c.score for c in ranked] == [90, 20]


def test_rerank_sem_tool_use_devolve_os_candidatos_intactos():
    candidates = [clip(0, 3), clip(4, 7)]
    client = FakeClient(FakeResponse([FakeTextBlock()]))

    ranked = rerank_candidates(candidates, build_transcription(), build_kb(), client=client, seed=1)

    assert len(ranked) == 2
    assert [c.score for c in ranked] == [50, 50]


def test_rerank_com_lista_vazia_nao_chama_a_api():
    client = rerank_client([])

    assert rerank_candidates([], build_transcription(), build_kb(), client=client) == []
    assert client.messages.calls == []


# --- embaralhamento -------------------------------------------------------


def test_shuffle_com_a_mesma_seed_produz_a_mesma_ordem():
    candidates = [clip(0, 3), clip(4, 7), clip(8, 11)]

    ordens = []
    for _ in range(2):
        client = rerank_client([])
        rerank_candidates(candidates, build_transcription(), build_kb(), client=client, seed=42)
        ordens.append(_sent_start_ids(client))

    assert ordens[0] == ordens[1]


def test_shuffle_com_seeds_diferentes_produz_ordens_diferentes():
    candidates = [clip(index * 4, index * 4 + 3) for index in range(3)]

    ordens = set()
    for seed in range(12):
        client = rerank_client([])
        rerank_candidates(candidates, build_transcription(), build_kb(), client=client, seed=seed)
        ordens.add(tuple(_sent_start_ids(client)))

    assert len(ordens) > 1


# --- prompt e chamada -----------------------------------------------------


def test_rerank_forca_a_tool_e_marca_o_cache_do_dossie():
    client = rerank_client([entry(0, 70)])

    rerank_candidates([clip(0, 3)], build_transcription(), build_kb(), client=client)
    request = client.messages.calls[0]

    assert request["tool_choice"] == {"type": "tool", "name": RERANK_TOOL_NAME}
    assert [tool["name"] for tool in request["tools"]] == [RERANK_TOOL_NAME]
    assert request["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "Pauta de exemplo: transparencia fiscal." in request["system"][-1]["text"]
    assert "ORDEM ALEATORIA" in request["system"][0]["text"]


def test_prompt_avisa_que_a_ordem_e_aleatoria_e_traz_o_texto_do_trecho():
    prompt = build_rerank_prompt([clip(4, 7), clip(8, 11)], build_transcription())

    assert "2 candidatos ja validados, em ordem aleatoria." in prompt
    assert "Texto: p4 p5 p6 p7" in prompt
    assert "Texto: p8 p9 p10 p11" in prompt
    assert "[0] " in prompt and "[1] " in prompt


def test_prompt_nao_vaza_a_transcricao_inteira():
    prompt = build_rerank_prompt([clip(4, 7)], build_transcription())

    assert "p0" not in prompt
    assert "p11" not in prompt


# --- uso encadeado --------------------------------------------------------


def test_select_clips_seguido_de_rerank_devolve_a_ordem_do_juiz():
    transcription = build_transcription()
    kb = build_kb()

    selection_client = FakeClient(
        FakeResponse(
            [
                FakeToolUseBlock(
                    TOOL_NAME,
                    {
                        "candidates": [
                            {
                                "start_word_id": 0,
                                "end_word_id": 3,
                                "format": SHORT_FORMAT,
                                "score": 90,
                                "justificativa": "achado 1",
                            },
                            {
                                "start_word_id": 8,
                                "end_word_id": 11,
                                "format": SHORT_FORMAT,
                                "score": 40,
                                "justificativa": "achado 2",
                            },
                        ]
                    },
                )
            ]
        )
    )

    candidates = select_clips(transcription, kb, client=selection_client)
    assert [c.start_word_id for c in candidates] == [0, 8]

    judge_client = rerank_client([entry(1, 95), entry(0, 30)])
    reranked = rerank_candidates(candidates, transcription, kb, client=judge_client, seed=0)
    sent = _sent_start_ids(judge_client)

    assert [c.start_word_id for c in reranked] == [sent[1], sent[0]]
    assert [c.score for c in reranked] == [95, 30]


def _sent_start_ids(client: FakeClient) -> list[int]:
    """Recupera, pelo prompt enviado, a ordem embaralhada em que os candidatos foram apresentados."""
    prompt = client.messages.calls[0]["messages"][0]["content"]
    transcription = build_transcription()
    order: list[int] = []
    for block in prompt.split("\n\n"):
        if not block.startswith("["):
            continue
        texto = next(line for line in block.splitlines() if line.startswith("Texto: "))
        first_word = texto.removeprefix("Texto: ").split(" ")[0]
        order.append(next(w.id for w in transcription.words if w.text == first_word))
    return order
