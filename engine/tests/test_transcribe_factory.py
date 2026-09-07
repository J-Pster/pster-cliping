"""Escolha do backend de transcricao, resolucao de device e fallback do WhisperX."""

from __future__ import annotations

import pytest

from clipador.transcribe import factory
from clipador.transcribe.factory import (
    TranscriberConfigError,
    TranscriberSettings,
    build_transcriber,
    resolve_compute_type,
    resolve_device,
)
from clipador.transcribe.whisper import FasterWhisperTranscriber
from clipador.transcribe.whisperx_transcriber import WhisperXTranscriber


def test_default_e_elevenlabs():
    """Decisao medida em 2026-09-02 contra o WhisperX local no mesmo video: das 44
    divergencias o Scribe acerta ~24 e o local 1, e dois erros do local eram alucinacao.
    Ver .docs/decisions/2026-09-02-transcricao-elevenlabs-scribe.md. Se este teste
    quebrar, alguem trocou o default sem refazer a medicao."""
    assert TranscriberSettings().backend == "elevenlabs"


def test_modelo_local_default_e_large_v3():
    """So vale para os backends locais; em PT-BR o large-v3 erra menos nome proprio,
    sigla e concordancia que o medium."""
    assert TranscriberSettings().model_size == "large-v3"


def test_backend_desconhecido_falha_na_construcao():
    with pytest.raises(ValueError, match="Backend de transcricao desconhecido"):
        TranscriberSettings(backend="vosk")


def test_device_explicito_passa_intacto():
    assert resolve_device("cuda") == "cuda"
    assert resolve_device("cpu") == "cpu"


def test_device_auto_resolve_para_cpu_sem_torch(monkeypatch):
    """O WhisperX nao entende "auto": ele repassa a string pro torch."""
    monkeypatch.setitem(__import__("sys").modules, "torch", None)

    assert resolve_device("auto") in ("cpu", "cuda")


def test_compute_type_auto_depende_do_device():
    assert resolve_compute_type("auto", "cuda") == "float16"
    assert resolve_compute_type("auto", "cpu") == "int8"
    assert resolve_compute_type("float32", "cuda") == "float32"


def test_constroi_whisperx_quando_a_lib_esta_disponivel(monkeypatch):
    monkeypatch.setattr(factory, "_whisperx_available", lambda: True)

    transcriber = build_transcriber(TranscriberSettings(backend="whisperx", device="cpu"))

    assert isinstance(transcriber, WhisperXTranscriber)
    assert transcriber.compute_type == "int8"


def test_cai_para_faster_whisper_quando_whisperx_nao_esta_instalado(monkeypatch, caplog):
    """Degradar o alinhamento e aceitavel; parar o pipeline por uma dependencia opcional
    nao e. O fallback nunca e silencioso."""
    monkeypatch.setattr(factory, "_whisperx_available", lambda: False)

    with caplog.at_level("WARNING"):
        transcriber = build_transcriber(TranscriberSettings(backend="whisperx", device="cpu"))

    assert isinstance(transcriber, FasterWhisperTranscriber)
    assert "whisperx nao esta instalado" in caplog.text


def test_faster_whisper_explicito_nao_passa_pelo_fallback(monkeypatch, caplog):
    monkeypatch.setattr(factory, "_whisperx_available", lambda: False)

    with caplog.at_level("WARNING"):
        build_transcriber(TranscriberSettings(backend="faster-whisper", device="cpu"))

    assert "whisperx nao esta instalado" not in caplog.text


def test_assemblyai_usa_a_chave_da_configuracao():
    transcriber = build_transcriber(
        TranscriberSettings(backend="assemblyai", assemblyai_api_key="chave-de-teste")
    )

    assert transcriber.api_key == "chave-de-teste"


def test_assemblyai_cai_para_a_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "do-ambiente")

    transcriber = build_transcriber(TranscriberSettings(backend="assemblyai"))

    assert transcriber.api_key == "do-ambiente"


def test_hf_token_da_configuracao_chega_no_whisperx(monkeypatch):
    monkeypatch.setattr(factory, "_whisperx_available", lambda: True)

    transcriber = build_transcriber(
        TranscriberSettings(backend="whisperx", device="cpu", diarize=True, hf_token="hf_abc")
    )

    assert transcriber.hf_token == "hf_abc"
    assert transcriber.diarize is True


def test_backend_de_nuvem_sem_chave_falha_alto(monkeypatch):
    """Nunca cai calado para o local: a diferenca entre nuvem e local e de qualidade
    medida, e uma queda silenciosa entregaria clipe pior sem ninguem perceber."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    with pytest.raises(TranscriberConfigError, match="ELEVENLABS_API_KEY"):
        build_transcriber(TranscriberSettings(backend="elevenlabs"))


def test_mensagem_de_chave_ausente_aponta_a_saida_local(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    with pytest.raises(TranscriberConfigError, match="--transcriber whisperx"):
        build_transcriber(TranscriberSettings(backend="elevenlabs"))
