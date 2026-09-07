"""Cliente HTTP GraphQL de baixo nivel pra API do Buffer (https://api.buffer.com).

Conta unica (API key pessoal do usuario, nao OAuth multi-tenant): a chave da
`Authorization: Bearer` da acesso a todas as orgs/canais dessa conta.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

from clipador.publish.models import PublishError

load_dotenv(override=True)

API_URL = "https://api.buffer.com"


def _api_key() -> str:
    api_key = os.environ.get("BUFFER_API_KEY")
    if not api_key:
        raise PublishError("BUFFER_API_KEY nao esta definida no .env")
    return api_key


def graphql_request(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Faz um POST GraphQL na API do Buffer e retorna o campo `data` da resposta."""
    response = requests.post(
        API_URL,
        json={"query": query, "variables": variables or {}},
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        window = None
        try:
            window = response.json().get("extensions", {}).get("window")
        except ValueError:
            pass
        detail = f"retry-after={retry_after}s" if retry_after else f"window={window}" if window else "sem detalhe"
        raise PublishError(f"Buffer: rate limit excedido (429, {detail})")

    if not response.ok:
        raise PublishError(f"Buffer: HTTP {response.status_code} ao chamar a API: {response.text}")

    payload = response.json()
    errors = payload.get("errors")
    if errors:
        messages = "; ".join(error.get("message", str(error)) for error in errors)
        raise PublishError(f"Buffer: erro GraphQL: {messages}")

    return payload.get("data", {})
