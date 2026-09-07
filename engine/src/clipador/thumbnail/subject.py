"""Escolhe, POR CLIPE, qual figura publica cadastrada (se alguma) e o assunto visual da
thumbnail - nunca um default fixo por categoria/canal. Corrige o defeito relatado pelo
usuario: o gerador de thumbnail anexava sempre a mesma pessoa (o apresentador do canal)
como referencia facial, mesmo em clipes cujo CONTEUDO era sobre outra figura publica ou
sobre nenhuma pessoa em especifico.

So o NOME das pessoas disponiveis (e uma frase por clipe) entra no prompt desta escolha,
nunca as fotos delas: quem manda foto de verdade pro gerador de imagem e so a UMA
escolhida aqui (ver `AIThumbnailGenerator.generate(..., subject=...)`), entao o contexto
da chamada que GERA a imagem nunca cresce com o tamanho da biblioteca de referencias.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from clipador.llm.provider import MODEL_ID, get_client
from clipador.select.models import ClipCandidate
from clipador.thumbnail.face_library import PoliticalFigure, available_figures

TOOL_NAME = "select_thumbnail_subject"
NONE_OPTION = "nenhuma"


def build_subject_tool(figures: tuple[PoliticalFigure, ...]) -> dict[str, Any]:
    options = [NONE_OPTION, *(figure.slug for figure in figures)]
    catalog = "\n".join(f"- {figure.slug}: {figure.display_name}" for figure in figures)
    return {
        "name": TOOL_NAME,
        "description": (
            "Escolhe qual figura publica cadastrada (se alguma) e o assunto visual deste "
            "trecho, para a thumbnail poder usar a foto de referencia certa."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "enum": options,
                    "description": (
                        "Pessoas cadastradas com foto de referencia disponivel:\n"
                        f"{catalog}\n\n"
                        "Escolha o identificador de UMA delas SE E SOMENTE SE este trecho "
                        "especifico for genuinamente SOBRE essa pessoa (ela e o assunto "
                        "central do que esta sendo dito aqui - uma decisao dela, uma "
                        "declaracao dela, algo que aconteceu com ela - nao uma mencao de "
                        "passagem ou uma citacao rapida). Quando o trecho e narrado/comentado "
                        "por alguem da lista falando sobre um assunto qualquer (opiniao, "
                        "analise), essa pessoa TAMBEM conta como assunto valido, pois e ela "
                        f"quem aparece na cena. Caso contrario, ou se nenhuma pessoa da lista "
                        f"for claramente o assunto deste trecho, responda '{NONE_OPTION}' - "
                        "nunca force uma escolha so pra preencher o campo."
                    ),
                }
            },
            "required": ["subject"],
            "additionalProperties": False,
        },
    }


def build_subject_prompt(candidate: ClipCandidate, transcription_excerpt: str) -> str:
    return (
        "Decida o assunto visual deste trecho de video usando SO o texto abaixo (nao "
        "adivinhe por outro conhecimento seu sobre o video).\n\n"
        f"Transcricao do trecho:\n{transcription_excerpt}\n\n"
        f"Justificativa da selecao original deste trecho: {candidate.justificativa}"
    )


def select_thumbnail_subject(
    candidate: ClipCandidate,
    transcription_excerpt: str,
    client: Any | None = None,
    model: str = MODEL_ID,
    max_tokens: int = 300,
    figures: tuple[PoliticalFigure, ...] | None = None,
) -> PoliticalFigure | None:
    """Devolve a figura escolhida, ou None quando nenhuma se aplica (o caso mais comum) ou
    quando a biblioteca esta vazia (nenhuma foto cadastrada ainda - custo zero nesse caso,
    nem chama o LLM)."""
    available = figures if figures is not None else available_figures()
    if not available:
        return None

    api = client if client is not None else get_client()
    tool = build_subject_tool(available)
    response = api.messages.create(
        model=model,
        max_tokens=max_tokens,
        tools=[tool],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[
            {"role": "user", "content": build_subject_prompt(candidate, transcription_excerpt)}
        ],
    )

    payload = _extract_payload(response)
    slug = str(payload.get("subject", NONE_OPTION))
    if slug == NONE_OPTION:
        return None
    return next((figure for figure in available if figure.slug == slug), None)


def _extract_payload(response: Any) -> Mapping[str, Any]:
    for block in _attr(response, "content") or []:
        if _attr(block, "type") == "tool_use" and _attr(block, "name") == TOOL_NAME:
            return _attr(block, "input") or {}
    return {}


def _attr(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)
