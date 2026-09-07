"""Enfase semantica da legenda: quais palavras do trecho merecem cor propria.

Uma legenda em que TODA palavra tem o mesmo peso obriga o espectador a ler tudo pra achar
o que importa. Marcar 1 em cada 8-10 palavras com uma cor propria da um ponto de fixacao
por cue, que e o que as ferramentas de clipe fazem manualmente.

Isso NAO e derivavel de heuristica lexica (frequencia, tamanho da palavra, classe
gramatical): a palavra que carrega o gancho de um trecho e uma questao de sentido, nao de
forma. Por isso e uma chamada de LLM, com o mesmo contrato de tool use forcado que
selecao e metadados usam.

Custo: uma chamada por clipe, alem da de metadados. Por isso e OPT-IN
(`PipelineConfig.subtitle_emphasis`, `--subtitle-emphasis` na CLI) e nao default.

A saida do modelo e entrada de sistema nao controlado: os indices sao validados uma vez
aqui, na fronteira, e o resto do pipeline recebe um `frozenset` de `word_id` que sabe ser
valido.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from clipador.llm.provider import MODEL_ID, get_client
from clipador.transcribe.models import Word

logger = logging.getLogger(__name__)

TOOL_NAME = "mark_emphasis"
# Uma palavra destacada a cada ~9 mantem o efeito de ponto de fixacao. Acima disso o
# destaque deixa de destacar: se tudo e colorido, nada e.
WORDS_PER_EMPHASIS = 9
MAX_EMPHASIS_WORDS = 24

SYSTEM_PROMPT = (
    "Voce marca palavras-chave para destaque colorido na legenda queimada de um clipe "
    "curto de video. Escolha as palavras que carregam o SENTIDO do trecho: o substantivo "
    "concreto, o numero, o nome proprio, o verbo da acao, o termo que faz o espectador "
    "parar o scroll. Nunca marque artigo, preposicao, conjuncao, pronome atono nem verbo "
    "de ligacao. Marque no maximo uma palavra por frase curta, e nunca duas palavras "
    "seguidas. Responda somente pela ferramenta."
)


def build_emphasis_tool(max_words: int) -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Registra quais palavras do trecho recebem destaque de cor na legenda, "
            "pelo indice mostrado ao lado de cada palavra."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "indices": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "maxItems": max_words,
                    "description": (
                        "Indices (o numero entre colchetes) das palavras a destacar, em "
                        "ordem crescente. Pode vir vazio se nenhuma palavra se destacar."
                    ),
                }
            },
            "required": ["indices"],
        },
    }


def build_user_prompt(words: Sequence[Word], max_words: int) -> str:
    numbered = " ".join(f"[{index}]{word.text}" for index, word in enumerate(words))
    return (
        f"Trecho do clipe, com o indice de cada palavra entre colchetes:\n\n{numbered}\n\n"
        f"Marque no maximo {max_words} palavra(s) para destaque."
    )


def _budget(word_count: int) -> int:
    return max(1, min(MAX_EMPHASIS_WORDS, word_count // WORDS_PER_EMPHASIS))


def _attr(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _extract_indices(response: Any) -> list[Any]:
    for block in _attr(response, "content") or []:
        if _attr(block, "type") == "tool_use" and _attr(block, "name") == TOOL_NAME:
            payload: Mapping[str, Any] = _attr(block, "input") or {}
            return list(payload.get("indices", []))
    return []


def _valid_word_ids(raw_indices: Sequence[Any], words: Sequence[Word], budget: int) -> frozenset[int]:
    """Converte os indices locais devolvidos pelo modelo em `word_id` globais, descartando
    o que nao existe. Indice fora da faixa e sinal de resposta malformada, nao de erro
    recuperavel do pipeline: avisa e ignora aquele indice."""
    selected: list[int] = []
    for raw in raw_indices:
        try:
            index = int(raw)
        except (TypeError, ValueError):
            logger.warning("Enfase: indice nao numerico devolvido pelo LLM: %r", raw)
            continue
        if not 0 <= index < len(words):
            logger.warning(
                "Enfase: indice %d fora da faixa 0..%d devolvida pelo LLM", index, len(words) - 1
            )
            continue
        selected.append(words[index].id)
    return frozenset(selected[:budget])


def select_emphasis_word_ids(
    words: Sequence[Word],
    client: Any | None = None,
    model: str = MODEL_ID,
    max_tokens: int = 1000,
) -> frozenset[int]:
    """`word_id` das palavras do trecho que recebem cor de enfase na legenda."""
    if not words:
        return frozenset()

    budget = _budget(len(words))
    api = client if client is not None else get_client()
    response = api.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        tools=[build_emphasis_tool(budget)],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[{"role": "user", "content": build_user_prompt(words, budget)}],
    )
    word_ids = _valid_word_ids(_extract_indices(response), words, budget)
    logger.info("Enfase: %d palavra(s) destacada(s) de %d", len(word_ids), len(words))
    return word_ids
