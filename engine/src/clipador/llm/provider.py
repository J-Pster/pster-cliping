"""Dispatcher de provedor de LLM de TEXTO do motor: Claude ou Gemini, via env var.

Selecao, rerank e geracao de metadados (`select/selector.py`, `select/rerank.py`,
`metadata/generator.py`) chamam `.messages.create(...)` no formato da Messages API da
Anthropic (tool use forcado pra saida estruturada). Trocar `CLIPADOR_TEXT_LLM_PROVIDER`
so troca QUEM implementa esse mesmo contrato (`clipador.llm.claude_client` ou
`clipador.llm.gemini_client`) - nenhum dos tres call sites muda.

A geracao de IMAGEM da thumbnail (`thumbnail/ai_thumbnail.py`) e SEMPRE Gemini,
independente desta variavel: so o texto (selecao/rerank/metadados) e configuravel.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(override=True)  # .env do projeto sempre vence env var solta do sistema

TEXT_LLM_PROVIDER = os.environ.get("CLIPADOR_TEXT_LLM_PROVIDER", "claude").strip().lower()

if TEXT_LLM_PROVIDER == "claude":
    from clipador.llm.claude_client import MODEL_ID, get_client
elif TEXT_LLM_PROVIDER == "gemini":
    from clipador.llm.gemini_client import MODEL_ID, get_client
else:
    raise RuntimeError(
        f"CLIPADOR_TEXT_LLM_PROVIDER invalido: {TEXT_LLM_PROVIDER!r} (use 'claude' ou 'gemini')"
    )

__all__ = ["MODEL_ID", "TEXT_LLM_PROVIDER", "get_client"]
