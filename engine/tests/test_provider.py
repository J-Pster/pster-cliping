"""Testa o dispatch de CLIPADOR_TEXT_LLM_PROVIDER em clipador.llm.provider.

O modulo le a env var e escolhe o backend NO IMPORT (mesmo padrao ja usado por
CLIPADOR_LLM_AUTH_MODE em claude_client.py), entao o teste precisa recarregar o modulo
apos mudar a env var em vez de so importar uma vez.
"""

from __future__ import annotations

import importlib

import pytest

import clipador.llm.provider as provider


def _reload_with(monkeypatch: pytest.MonkeyPatch, value: str | None):
    # O `.env` real do projeto define CLIPADOR_TEXT_LLM_PROVIDER, e o modulo chama
    # `load_dotenv(override=True)` (".env sempre vence env var solta") - sem neutralizar
    # isso aqui, o reload releria o arquivo e sobrescreveria o monkeypatch abaixo.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    if value is None:
        monkeypatch.delenv("CLIPADOR_TEXT_LLM_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("CLIPADOR_TEXT_LLM_PROVIDER", value)
    return importlib.reload(provider)


@pytest.fixture(autouse=True)
def _restore_default_provider(monkeypatch):
    yield
    _reload_with(monkeypatch, None)


def test_default_sem_env_usa_claude(monkeypatch):
    reloaded = _reload_with(monkeypatch, None)

    assert reloaded.TEXT_LLM_PROVIDER == "claude"
    from clipador.llm.claude_client import MODEL_ID as CLAUDE_MODEL_ID

    assert reloaded.MODEL_ID == CLAUDE_MODEL_ID


def test_gemini_troca_o_backend(monkeypatch):
    reloaded = _reload_with(monkeypatch, "gemini")

    assert reloaded.TEXT_LLM_PROVIDER == "gemini"
    from clipador.llm.gemini_client import MODEL_ID as GEMINI_MODEL_ID

    assert reloaded.MODEL_ID == GEMINI_MODEL_ID


def test_case_insensitive_e_com_espacos(monkeypatch):
    reloaded = _reload_with(monkeypatch, "  GEMINI  ")

    assert reloaded.TEXT_LLM_PROVIDER == "gemini"


def test_valor_invalido_levanta_erro_claro(monkeypatch):
    with pytest.raises(RuntimeError, match="CLIPADOR_TEXT_LLM_PROVIDER invalido"):
        _reload_with(monkeypatch, "chatgpt")
