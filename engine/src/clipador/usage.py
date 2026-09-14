"""Rastreamento de consumo de tokens/API por chamada de LLM, geracao de imagem ou
transcricao em nuvem.

Duas saidas pro mesmo evento: (1) callback de progresso (`configure`), pra uma UI externa
mostrar um contador em tempo real por provedor durante a execucao (ver
clipador.progress); (2) arquivo JSONL append-only em `usage-logs/usage.jsonl`, relativo
ao cwd do processo - mesma convencao de kb/, .env e assets/fonts/ (cwd e sempre a raiz
gravavel do engine, ver runtime-paths.ts::workDir() do lado do app) - uma linha por
chamada, pronta pra coleta offline depois. O log em disco SEMPRE acontece, mesmo sem UI
acoplada (CLI direta, testes que nao chamam `configure`); o callback de progresso e so
quem opcionalmente ouve em tempo real.

`run_id` agrupa todas as chamadas de UMA execucao: gerado uma vez por PROCESSO (o app
sempre spawna um processo Python novo por job, ver app/src/main/ipc/engine.ts::
runEngine), entao nao precisa ser passado explicitamente por quem chama `record()`.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clipador.progress import OnProgress, ProgressEvent, noop_progress

logger = logging.getLogger(__name__)

USAGE_LOG_DIRNAME = "usage-logs"
USAGE_LOG_FILENAME = "usage.jsonl"

_run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
_on_usage: OnProgress = noop_progress


def configure(on_progress: OnProgress) -> None:
    """Liga o contador em tempo real da UI. Chamar uma vez no inicio de run_pipeline/
    rebrand_batch. Opcional: sem chamar, o log em disco continua acontecendo normalmente,
    so ninguem recebe o evento ao vivo."""
    global _on_usage
    _on_usage = on_progress


def _append_to_log(event: dict[str, Any]) -> None:
    # Falha em gravar o log de consumo NUNCA derruba o pipeline: e observabilidade sobre
    # uma chamada que ja completou com sucesso quando record() e chamado, nao a chamada
    # em si. Fica visivel no log humano (WARNING), so nao interrompe a execucao.
    try:
        log_dir = Path.cwd() / USAGE_LOG_DIRNAME
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / USAGE_LOG_FILENAME, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Nao foi possivel gravar log de consumo (%s): %s", event.get("provider"), exc)


def record(
    provider: str,
    operation: str,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    characters: int | None = None,
    audio_seconds: float | None = None,
    images: int | None = None,
) -> None:
    """Registra o consumo de uma chamada ja concluida. Todos os campos de quantidade sao
    opcionais porque cada provedor fatura por unidades diferentes (Claude/Gemini texto:
    tokens; Gemini imagem: por imagem, tokens quando disponiveis; ElevenLabs: segundos de
    audio)."""
    event: ProgressEvent = {
        "event": "usage",
        "run_id": _run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "operation": operation,
    }
    if input_tokens is not None:
        event["input_tokens"] = input_tokens
    if output_tokens is not None:
        event["output_tokens"] = output_tokens
    if characters is not None:
        event["characters"] = characters
    if audio_seconds is not None:
        event["audio_seconds"] = audio_seconds
    if images is not None:
        event["images"] = images

    _on_usage(event)
    _append_to_log(dict(event))
