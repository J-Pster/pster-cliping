"""Eventos de progresso do pipeline, para consumo por uma UI externa (ex. local-use).

`run_pipeline`/`rebrand_batch` recebem um callback opcional `on_progress` e chamam ele
em pontos-chave (fase atual, plano de clipes, clipe iniciado/concluido/falhou). O default
e um no-op: o custo de montar e imprimir progresso so existe quando alguem pediu, mesma
convencao de injecao de dependencia do resto do pipeline.

`print_progress` e o callback pronto pra CLI: imprime cada evento como uma linha
"CLIPADOR_PROGRESS <json>" em stdout, junto do log humano existente (logging vai pra
stderr). Uma ferramenta consumidora filtra por esse marcador; um humano rodando a CLI
direto so ve uma linha extra por evento.
"""

from __future__ import annotations

import json
from typing import Callable, TypedDict

MARKER = "CLIPADOR_PROGRESS "


class ProgressEvent(TypedDict, total=False):
    event: str  # "phase" | "plan" | "clip_start" | "clip_done" | "clip_failed"
    phase: str
    message: str
    index: int
    total: int
    clip_id: str
    format: str
    directory: str
    status: str
    stage: str


OnProgress = Callable[[ProgressEvent], None]


def noop_progress(_event: ProgressEvent) -> None:
    return None


def print_progress(event: ProgressEvent) -> None:
    print(f"{MARKER}{json.dumps(event, ensure_ascii=False)}", flush=True)
