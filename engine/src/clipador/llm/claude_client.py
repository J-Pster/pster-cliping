from __future__ import annotations

import os
from typing import Any

from dotenv import find_dotenv, load_dotenv

from clipador import usage

# ver comentario em clipador/llm/provider.py: sem find_dotenv(usecwd=True), dotenv
# procura .env a partir da pasta deste arquivo, nao do cwd do processo.
load_dotenv(find_dotenv(usecwd=True), override=True)

MODEL_ID = "claude-sonnet-5"

# O SDK oficial ja reage sozinho a falha transiente (429/500/504/529) com
# backoff exponencial + jitter, honrando o header retry-after quando existe -
# o default da lib e so 2 tentativas, baixo pra um pipeline batch que roda sem
# supervisao (varios clipes, cada um com 2-3 chamadas). Subir pra 5 aqui e a
# unica mudanca necessaria; nao ha motivo pra reimplementar isso com tenacity.
DEFAULT_MAX_RETRIES = 5


# "api_key": ANTHROPIC_API_KEY, cobranca pay-per-use direto na conta de API.
# "oauth": CLAUDE_CODE_OAUTH_TOKEN (gerado via `claude setup-token`), consome a
# cota da assinatura Claude Pro/Max da conta logada em vez de credito de API.
# chave ausente e chave vazia (`.env` sempre grava todo ENV_KEYS, ver
# app/src/main/ipc/settings.ts) significam a mesma coisa, "nao configurado".
AUTH_MODE = (os.environ.get("CLIPADOR_LLM_AUTH_MODE") or "oauth").strip().lower()


class _UsageTrackingMessages:
    """Encapsula `.messages` so pra registrar consumo apos cada chamada - o objeto
    `response` que devolve e o mesmo da SDK oficial, sem nenhuma traducao (ao contrario
    do adaptador Gemini, os tres call sites leem `response.content` real da Anthropic)."""

    def __init__(self, messages: Any) -> None:
        self._messages = messages

    def create(self, **kwargs: Any) -> Any:
        response = self._messages.create(**kwargs)
        response_usage = getattr(response, "usage", None)
        if response_usage is not None:
            usage.record(
                "claude",
                "text",
                input_tokens=getattr(response_usage, "input_tokens", None),
                output_tokens=getattr(response_usage, "output_tokens", None),
            )
        return response


class _UsageTrackingClient:
    def __init__(self, client: Any) -> None:
        self.messages = _UsageTrackingMessages(client.messages)


def get_client(max_retries: int = DEFAULT_MAX_RETRIES) -> Any:
    import anthropic

    if AUTH_MODE == "oauth":
        token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if not token:
            raise RuntimeError(
                "CLAUDE_CODE_OAUTH_TOKEN nao esta definida no ambiente "
                "(gere com `claude setup-token`, verifique o arquivo .env)"
            )
        return _UsageTrackingClient(anthropic.Anthropic(auth_token=token, max_retries=max_retries))

    if AUTH_MODE == "api_key":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY nao esta definida no ambiente (verifique o arquivo .env)"
            )
        return _UsageTrackingClient(anthropic.Anthropic(api_key=api_key, max_retries=max_retries))

    raise RuntimeError(
        f"CLIPADOR_LLM_AUTH_MODE invalido: {AUTH_MODE!r} (use 'oauth' ou 'api_key')"
    )


def test_connection() -> bool:
    try:
        client = get_client()
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=16,
            messages=[{"role": "user", "content": "Responda apenas 'ok'."}],
        )
        text = next((block.text for block in response.content if block.type == "text"), "")
        return "ok" in text.strip().lower()
    except Exception:
        return False
