"""Adaptador Gemini pro mesmo contrato de `.messages.create(...)` usado pelos tres call
sites de LLM de TEXTO do motor (selecao, rerank, geracao de metadados) - ver
`clipador.llm.provider`. A geracao de IMAGEM da thumbnail (`thumbnail/ai_thumbnail.py`)
e sempre Gemini e nao passa por aqui, independente do provedor escolhido pra texto.

Traduz o forced tool-use da Messages API da Anthropic (`tools=[...]`,
`tool_choice={"type": "tool", "name": ...}`) pro forced function-calling do Gemini
(`FunctionCallingConfig(mode="ANY", allowed_function_names=[...])`) e devolve a resposta
ja no formato que `_attr(response, "content")` dos tres call sites espera: um bloco com
`type == "tool_use"`, `name` e `input` (dict com os argumentos).
"""

from __future__ import annotations

import os
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=True)  # .env do projeto sempre vence env var solta do sistema

# Pro (nao Flash): selecao/rerank/metadados pedem o mesmo nivel de raciocinio que o
# Claude Sonnet faz hoje - fica configuravel via env pra quem quiser trocar por um Flash
# mais barato/rapido, ou apontar pra uma versao mais nova sem mexer em codigo.
MODEL_ID = os.environ.get("CLIPADOR_GEMINI_TEXT_MODEL", "").strip() or "gemini-3.1-pro-preview"

DEFAULT_MAX_RETRIES = 5

# Chaves da JSON Schema (convencao Anthropic) sem campo equivalente na REST API do
# Gemini: o SDK aceita "additionalProperties" localmente (so valida por alias), mas o
# SERVIDOR rejeita a chamada inteira com 400 INVALID_ARGUMENT se ela sobreviver no
# payload - confirmado em teste real, nao e suposicao.
_UNSUPPORTED_SCHEMA_KEYS = {"additionalProperties", "strict"}


def _strip_unsupported_schema_keys(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: _strip_unsupported_schema_keys(value)
            for key, value in node.items()
            if key not in _UNSUPPORTED_SCHEMA_KEYS
        }
    if isinstance(node, list):
        return [_strip_unsupported_schema_keys(item) for item in node]
    return node


def _system_text(system: list[dict[str, Any]] | str | None) -> str | None:
    """Achata os blocos `[{"type": "text", "text": ..., "cache_control": ...}]` da
    Messages API num unico texto - o Gemini nao tem, nesta chamada, um equivalente ao
    `cache_control` explicito por bloco, entao o campo e apenas ignorado aqui."""
    if system is None:
        return None
    if isinstance(system, str):
        return system
    return "\n\n".join(block["text"] for block in system if block.get("text"))


class _ToolUseBlock:
    """Duck-type do bloco `tool_use` da Messages API - e o que `selector.py`,
    `rerank.py` e `metadata/generator.py` leem via `_attr(block, "type"/"name"/"input")`."""

    def __init__(self, name: str, input_: dict[str, Any]) -> None:
        self.type = "tool_use"
        self.name = name
        self.input = input_


class _Response:
    def __init__(self, content: list[Any]) -> None:
        self.content = content


class _Messages:
    def __init__(self, genai_client: Any, max_retries: int) -> None:
        self._client = genai_client
        self._max_retries = max_retries

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any],
        messages: list[dict[str, Any]],
        system: list[dict[str, Any]] | str | None = None,
    ) -> _Response:
        from google.genai import types

        if len(tools) != 1:
            raise NotImplementedError(
                "Adaptador Gemini so suporta forcar exatamente 1 tool por chamada "
                f"(recebeu {len(tools)}) - e o unico uso real dos tres call sites hoje."
            )
        content = messages[0]["content"] if len(messages) == 1 else None
        if len(messages) != 1 or messages[0]["role"] != "user" or not isinstance(content, str):
            raise NotImplementedError(
                "Adaptador Gemini so suporta uma unica mensagem de role 'user' com "
                "conteudo string - e o unico uso real dos tres call sites hoje."
            )

        tool_def = tools[0]
        declaration = types.FunctionDeclaration(
            name=tool_def["name"],
            description=tool_def.get("description", ""),
            parameters=_strip_unsupported_schema_keys(tool_def["input_schema"]),
        )
        config = types.GenerateContentConfig(
            system_instruction=_system_text(system),
            tools=[types.Tool(function_declarations=[declaration])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=[tool_choice.get("name", tool_def["name"])],
                )
            ),
            max_output_tokens=max_tokens,
        )

        attempts = max(1, self._max_retries)
        response = None
        for attempt in range(attempts):
            try:
                response = self._client.models.generate_content(
                    model=model, contents=content, config=config
                )
                break
            except Exception:
                if attempt == attempts - 1:
                    raise
                time.sleep(min(2**attempt, 30))

        blocks: list[Any] = []
        for candidate in getattr(response, "candidates", None) or []:
            parts = getattr(getattr(candidate, "content", None), "parts", None) or []
            for part in parts:
                call = getattr(part, "function_call", None)
                if call is not None:
                    blocks.append(_ToolUseBlock(call.name, dict(call.args or {})))
        return _Response(blocks)


class _GeminiMessagesClient:
    def __init__(self, genai_client: Any, max_retries: int) -> None:
        self.messages = _Messages(genai_client, max_retries)


def get_client(max_retries: int = DEFAULT_MAX_RETRIES) -> Any:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao esta definida no ambiente (verifique o arquivo .env)")

    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "google-genai indisponivel. Instale com: pip install 'clipador[thumbnail-ai]'"
        ) from exc

    return _GeminiMessagesClient(genai.Client(api_key=api_key), max_retries)


_TEST_TOOL: dict[str, Any] = {
    "name": "reply",
    "description": "Responde ok=true.",
    "input_schema": {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    },
}


def test_connection() -> bool:
    try:
        client = get_client()
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=16,
            tools=[_TEST_TOOL],
            tool_choice={"type": "tool", "name": "reply"},
            messages=[{"role": "user", "content": "Responda chamando a ferramenta com ok=true."}],
        )
        block = response.content[0]
        return bool(block.input.get("ok"))
    except Exception:
        return False
