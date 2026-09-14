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

from dotenv import find_dotenv, load_dotenv

# find_dotenv(usecwd=True): sem isso, dotenv busca o .env subindo a partir da pasta
# DESTE arquivo, nao do cwd do processo - no app empacotado este arquivo mora dentro do
# python embutido (resources/python/Lib/site-packages/...), bem longe do .env real em
# userData/engine-workspace. override=True: .env do projeto sempre vence env var solta
# do sistema.
load_dotenv(find_dotenv(usecwd=True), override=True)

# `.env` sempre grava esta chave, mesmo vazia (Settings escreve todo ENV_KEYS de uma vez,
# ver app/src/main/ipc/settings.ts): chave ausente E chave vazia significam a mesma coisa,
# "nao configurado", entao os dois caem no default.
TEXT_LLM_PROVIDER = (os.environ.get("CLIPADOR_TEXT_LLM_PROVIDER") or "claude").strip().lower()

if TEXT_LLM_PROVIDER == "claude":
    from clipador.llm.claude_client import MODEL_ID, get_client
elif TEXT_LLM_PROVIDER == "gemini":
    from clipador.llm.gemini_client import MODEL_ID, get_client
else:
    raise RuntimeError(
        f"CLIPADOR_TEXT_LLM_PROVIDER invalido: {TEXT_LLM_PROVIDER!r} (use 'claude' ou 'gemini')"
    )

__all__ = ["MODEL_ID", "TEXT_LLM_PROVIDER", "get_client"]
