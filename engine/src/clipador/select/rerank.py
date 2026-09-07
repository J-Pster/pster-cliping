"""Re-ranking listwise dos candidatos numa segunda chamada, separada da etapa de busca.

Achar candidato e julgar candidato sao tarefas diferentes: numa unica chamada o modelo
atribui score enquanto ainda esta varrendo a transcricao, e o score sai enviesado pela ordem
em que ele encontrou os trechos. Aqui os candidatos ja validados voltam embaralhados, sem a
transcricao inteira competindo por atencao, e sao julgados uns contra os outros por uma rubrica
explicita.

Esta etapa NAO e chamada por `select_clips`: ela custa uma segunda chamada de API e fica a
cargo de quem orquestra o pipeline decidir se vale. Uso encadeado:

    candidates = select_clips(transcription, kb, client=client)
    ranked = rerank_candidates(candidates, transcription, kb, client=client)
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from clipador import category as category_module
from clipador.kb.knowledge import KnowledgeBase
from clipador.llm.provider import MODEL_ID, get_client
from clipador.select.models import MAX_SCORE, MIN_SCORE, ClipCandidate
from clipador.transcribe.models import TranscriptionResult

RERANK_TOOL_NAME = "rank_clips"

RERANK_TOOL: dict[str, Any] = {
    "name": RERANK_TOOL_NAME,
    "description": (
        "Registra os candidatos ja apresentados na ordem ranqueada, do melhor para o pior. "
        "Use apenas os indices que aparecem na lista enviada, cada um uma unica vez."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "ranking": {
                "type": "array",
                "description": "Candidatos ordenados do melhor para o pior.",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "Indice do candidato na lista enviada.",
                        },
                        "score": {
                            "type": "integer",
                            "description": "Nota final de potencial de viralizacao, de 0 a 99.",
                        },
                        "justificativa": {
                            "type": "string",
                            "description": (
                                "Veredito curto citando os eixos da rubrica que decidiram a posicao."
                            ),
                        },
                    },
                    "required": ["index", "score", "justificativa"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["ranking"],
        "additionalProperties": False,
    },
}

_POLITICS_PERSON_RERANK_INSTRUCTIONS = """Voce julga clipes candidatos ja recortados de um video de um movimento politico.

A lista chega em ORDEM ALEATORIA de proposito. Posicao na lista nao diz nada sobre qualidade,
e o score inicial veio de uma primeira passagem apressada: trate os dois como ruido.

Compare os candidatos entre si nestes quatro eixos, nesta ordem de peso:
1. Gancho: os primeiros segundos param o scroll ou pedem paciencia?
2. Progressao: o trecho anda de um ponto a outro e fecha, ou fica dando voltas?
3. Valor percebido: quem assiste sai com uma ideia, uma frase ou uma emocao que valeu o tempo?
4. Alinhamento: puxa uma pauta prioritaria e o tom de voz do dossie abaixo, sem esbarrar nos
   temas sensiveis?

Ranqueie TODOS os candidatos recebidos, do melhor para o pior, e de nota de 0 a 99 a cada um.
Notas podem se repetir, mas a ordem precisa refletir sua decisao.

Responda exclusivamente chamando a ferramenta rank_clips."""

_GAMING_RERANK_INSTRUCTIONS = """Voce julga clipes candidatos ja recortados de uma gravacao de gameplay.

A lista chega em ORDEM ALEATORIA de proposito. Posicao na lista nao diz nada sobre qualidade,
e o score inicial veio de uma primeira passagem apressada: trate os dois como ruido.

Compare os candidatos entre si nestes quatro eixos, nesta ordem de peso:
1. Impacto do highlight: a jogada/eliminacao/virada e clara, forte e realmente aconteceu
   dentro do trecho (nao so sugerida)?
2. Gancho: os primeiros segundos ja mostram acao ou o setup imediato dela, sem enrolacao?
3. Clareza: da pra entender o que rolou sem ter visto o resto da sessao?
4. Payoff: o trecho fecha na reacao/consequencia do highlight, sem largar solto no meio da
   jogada seguinte?

Ranqueie TODOS os candidatos recebidos, do melhor para o pior, e de nota de 0 a 99 a cada um.
Notas podem se repetir, mas a ordem precisa refletir sua decisao.

Responda exclusivamente chamando a ferramenta rank_clips."""

_BOOK_AUDIOBOOK_RERANK_INSTRUCTIONS = """Voce julga clipes candidatos ja recortados de uma narracao/leitura de livro (audiobook), normalmente de nao-ficcao (politica, estrategia, negocios, tecnico, ensaio).

A lista chega em ORDEM ALEATORIA de proposito. Posicao na lista nao diz nada sobre qualidade,
e o score inicial veio de uma primeira passagem apressada: trate os dois como ruido.

Compare os candidatos entre si nestes quatro eixos, nesta ordem de peso:
1. Gancho: a frase de abertura prende por si so, sem depender de contexto anterior?
2. Virada/payoff: o trecho fecha numa conclusao forte, dado concreto ou argumento que
   realmente fecha o raciocinio (nao uma virada de enredo)?
3. Valor pratico/intelectual: quem ouve sai com um argumento, um dado ou um insight que
   valeu o tempo?
4. Fidelidade ao tom do narrador e ao dossie abaixo (quando houver), sem cortar no meio de
   um raciocinio ou descricao.

Ranqueie TODOS os candidatos recebidos, do melhor para o pior, e de nota de 0 a 99 a cada um.
Notas podem se repetir, mas a ordem precisa refletir sua decisao.

Responda exclusivamente chamando a ferramenta rank_clips."""

RERANK_INSTRUCTIONS_BY_CATEGORY: dict[str, str] = {
    category_module.POLITICS_PERSON: _POLITICS_PERSON_RERANK_INSTRUCTIONS,
    category_module.GAMING: _GAMING_RERANK_INSTRUCTIONS,
    category_module.BOOK_AUDIOBOOK: _BOOK_AUDIOBOOK_RERANK_INSTRUCTIONS,
}

# Mantido para quem ainda importa o nome antigo diretamente: sempre a variante politico/pessoa.
RERANK_INSTRUCTIONS = _POLITICS_PERSON_RERANK_INSTRUCTIONS


def rerank_candidates(
    candidates: Sequence[ClipCandidate],
    transcription: TranscriptionResult,
    kb: KnowledgeBase,
    client: Any | None = None,
    model: str = MODEL_ID,
    seed: int | None = None,
    max_tokens: int = 4000,
    category: str = category_module.DEFAULT_CATEGORY,
) -> list[ClipCandidate]:
    """Devolve copias dos candidatos reordenadas e com score reescrito pelo julgamento listwise.

    `seed` fixa o embaralhamento para os testes; em producao o default None embaralha de verdade,
    que e o que neutraliza o position bias do modelo.
    """
    if not candidates:
        return []

    shuffled = list(candidates)
    random.Random(seed).shuffle(shuffled)

    api = client if client is not None else get_client()
    response = api.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_build_system_blocks(kb, category),
        tools=[RERANK_TOOL],
        tool_choice={"type": "tool", "name": RERANK_TOOL_NAME},
        messages=[{"role": "user", "content": build_rerank_prompt(shuffled, transcription)}],
    )

    return _apply_ranking(shuffled, _extract_ranking(response))


def build_rerank_prompt(
    candidates: Sequence[ClipCandidate], transcription: TranscriptionResult
) -> str:
    blocks = [
        f"[{index}] {candidate.format} | {candidate.start:.1f}s-{candidate.end:.1f}s "
        f"({candidate.duration:.1f}s) | score da primeira passagem: {candidate.score}\n"
        f"Texto: {_clip_text(transcription, candidate)}\n"
        f"Justificativa da primeira passagem: {candidate.justificativa}"
        for index, candidate in enumerate(candidates)
    ]
    return (
        f"{len(candidates)} candidatos ja validados, em ordem aleatoria.\n\n"
        + "\n\n".join(blocks)
        + f"\n\nRanqueie os {len(candidates)} candidatos do melhor para o pior."
    )


def _build_system_blocks(
    kb: KnowledgeBase, category: str = category_module.DEFAULT_CATEGORY
) -> list[dict[str, Any]]:
    instructions = RERANK_INSTRUCTIONS_BY_CATEGORY[category_module.validate_category(category)]
    blocks: list[dict[str, Any]] = [{"type": "text", "text": instructions}]
    dossier = kb.dossier()
    if dossier:
        blocks.append({"type": "text", "text": dossier})
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def _apply_ranking(
    candidates: Sequence[ClipCandidate], ranking: Sequence[Any]
) -> list[ClipCandidate]:
    ranked: list[ClipCandidate] = []
    used: set[int] = set()
    for entry in ranking:
        index = _as_int(_attr(entry, "index"))
        if index is None or not 0 <= index < len(candidates) or index in used:
            continue
        used.add(index)
        candidate = candidates[index]
        score = _as_int(_attr(entry, "score"))
        justificativa = _attr(entry, "justificativa")
        ranked.append(
            replace(
                candidate,
                score=(
                    max(MIN_SCORE, min(MAX_SCORE, score)) if score is not None else candidate.score
                ),
                justificativa=str(justificativa) if justificativa else candidate.justificativa,
            )
        )

    # O que o modelo esqueceu de ranquear vai para o fim, intacto, em vez de sumir do pipeline.
    ranked.extend(
        replace(candidate)
        for index, candidate in enumerate(candidates)
        if index not in used
    )
    return ranked


def _clip_text(transcription: TranscriptionResult, candidate: ClipCandidate) -> str:
    return " ".join(
        word.text
        for word in transcription.words
        if candidate.start_word_id <= word.id <= candidate.end_word_id
    )


def _extract_ranking(response: Any) -> list[Any]:
    for block in _attr(response, "content") or []:
        if _attr(block, "type") == "tool_use" and _attr(block, "name") == RERANK_TOOL_NAME:
            payload = _attr(block, "input") or {}
            return list(payload.get("ranking", []))
    return []


def _attr(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
