from types import SimpleNamespace

import pytest

from clipador.llm.gemini_client import _strip_unsupported_schema_keys, _system_text

METADATA_LIKE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Titulo."},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
        },
        "nested": {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "additionalProperties": False,
        },
    },
    "required": ["title"],
    "additionalProperties": False,
}


def test_strip_unsupported_schema_keys_remove_em_qualquer_profundidade():
    stripped = _strip_unsupported_schema_keys(METADATA_LIKE_SCHEMA)

    assert "additionalProperties" not in stripped
    assert "additionalProperties" not in stripped["properties"]["nested"]
    assert stripped["properties"]["title"] == {"type": "string", "description": "Titulo."}
    assert stripped["required"] == ["title"]


def test_strip_unsupported_schema_keys_remove_strict_tambem():
    schema = {"strict": True, "type": "object", "properties": {}}

    assert _strip_unsupported_schema_keys(schema) == {"type": "object", "properties": {}}


def test_system_text_achata_blocos_com_cache_control():
    system = [
        {"type": "text", "text": "instrucoes"},
        {"type": "text", "text": "dossie", "cache_control": {"type": "ephemeral"}},
    ]

    assert _system_text(system) == "instrucoes\n\ndossie"


def test_system_text_aceita_string_direta():
    assert _system_text("ja e texto") == "ja e texto"


def test_system_text_none_devolve_none():
    assert _system_text(None) is None


# --- _Messages.create: traducao pro forced function-calling do Gemini -----------------


class FakeFunctionCall:
    def __init__(self, name: str, args: dict):
        self.name = name
        self.args = args


class FakeGenaiModels:
    def __init__(self, function_call: FakeFunctionCall | None, error: Exception | None = None):
        self._function_call = function_call
        self._error = error
        self.calls: list[dict] = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self._error is not None:
            raise self._error
        part = SimpleNamespace(function_call=self._function_call)
        candidate = SimpleNamespace(content=SimpleNamespace(parts=[part]))
        return SimpleNamespace(candidates=[candidate])


class FakeGenaiClient:
    def __init__(self, function_call: FakeFunctionCall | None, error: Exception | None = None):
        self.models = FakeGenaiModels(function_call, error)


def test_messages_create_devolve_tool_use_block_equivalente():
    from clipador.llm.gemini_client import _Messages

    genai_client = FakeGenaiClient(FakeFunctionCall("propose_metadata", {"title": "X"}))
    messages = _Messages(genai_client, max_retries=1)

    response = messages.create(
        model="gemini-3.1-pro-preview",
        max_tokens=100,
        system=[{"type": "text", "text": "instrucoes"}],
        tools=[
            {
                "name": "propose_metadata",
                "description": "desc",
                "strict": True,
                "input_schema": {
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                    "additionalProperties": False,
                },
            }
        ],
        tool_choice={"type": "tool", "name": "propose_metadata"},
        messages=[{"role": "user", "content": "gere o titulo"}],
    )

    assert len(response.content) == 1
    block = response.content[0]
    assert block.type == "tool_use"
    assert block.name == "propose_metadata"
    assert block.input == {"title": "X"}

    call = genai_client.models.calls[0]
    assert call["model"] == "gemini-3.1-pro-preview"
    assert call["contents"] == "gere o titulo"


def test_messages_create_recusa_mais_de_uma_tool():
    from clipador.llm.gemini_client import _Messages

    messages = _Messages(FakeGenaiClient(None), max_retries=1)

    with pytest.raises(NotImplementedError):
        messages.create(
            model="m",
            max_tokens=10,
            tools=[{"name": "a", "input_schema": {}}, {"name": "b", "input_schema": {}}],
            tool_choice={"type": "tool", "name": "a"},
            messages=[{"role": "user", "content": "x"}],
        )


def test_messages_create_recusa_mensagem_multipla():
    from clipador.llm.gemini_client import _Messages

    messages = _Messages(FakeGenaiClient(None), max_retries=1)

    with pytest.raises(NotImplementedError):
        messages.create(
            model="m",
            max_tokens=10,
            tools=[{"name": "a", "input_schema": {}}],
            tool_choice={"type": "tool", "name": "a"},
            messages=[
                {"role": "user", "content": "x"},
                {"role": "user", "content": "y"},
            ],
        )


def test_messages_create_sem_function_call_devolve_content_vazio():
    from clipador.llm.gemini_client import _Messages

    genai_client = FakeGenaiClient(None)
    messages = _Messages(genai_client, max_retries=1)

    response = messages.create(
        model="m",
        max_tokens=10,
        tools=[{"name": "a", "input_schema": {"type": "object", "properties": {}}}],
        tool_choice={"type": "tool", "name": "a"},
        messages=[{"role": "user", "content": "x"}],
    )

    assert response.content == []


def test_messages_create_tenta_de_novo_apos_falha_transiente(monkeypatch):
    from clipador.llm import gemini_client
    from clipador.llm.gemini_client import _Messages

    monkeypatch.setattr(gemini_client.time, "sleep", lambda _seconds: None)

    class FlakyModels(FakeGenaiModels):
        def __init__(self):
            super().__init__(FakeFunctionCall("a", {"ok": True}))
            self._attempts = 0

        def generate_content(self, *, model, contents, config):
            self._attempts += 1
            if self._attempts < 2:
                raise RuntimeError("503 transiente")
            return super().generate_content(model=model, contents=contents, config=config)

    genai_client = SimpleNamespace(models=FlakyModels())
    messages = _Messages(genai_client, max_retries=3)

    response = messages.create(
        model="m",
        max_tokens=10,
        tools=[{"name": "a", "input_schema": {"type": "object", "properties": {}}}],
        tool_choice={"type": "tool", "name": "a"},
        messages=[{"role": "user", "content": "x"}],
    )

    assert response.content[0].input == {"ok": True}
    assert genai_client.models._attempts == 2
