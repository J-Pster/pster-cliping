"""Testes do AssemblyAITranscriber - 100% offline, client sempre injetado, sem chamada real."""

from __future__ import annotations

import pytest

from clipador.transcribe.assemblyai_transcriber import (
    AssemblyAITranscriber,
    TranscriptionError,
    build_result_from_assemblyai,
)


class FakeWord:
    def __init__(self, text: str, start: int, end: int) -> None:
        self.text = text
        self.start = start
        self.end = end


class FakeUtterance:
    def __init__(self, speaker: str, words: list[FakeWord]) -> None:
        self.speaker = speaker
        self.words = words


class FakeTranscript:
    def __init__(
        self,
        words=None,
        utterances=None,
        status="completed",
        error=None,
        language_code="pt",
    ) -> None:
        self.words = words or []
        self.utterances = utterances
        self.status = status
        self.error = error
        self.language_code = language_code


class FakeClient:
    def __init__(self, transcript: FakeTranscript) -> None:
        self._transcript = transcript
        self.calls: list[tuple[str, object]] = []

    def transcribe(self, audio_path, config):
        self.calls.append((audio_path, config))
        return self._transcript


# --- build_result_from_assemblyai ------------------------------------------------


def test_build_result_sem_diarizacao_usa_um_segmento_unico():
    transcript = FakeTranscript(
        words=[FakeWord("Ola", 0, 500), FakeWord("mundo", 500, 1000)]
    )
    result = build_result_from_assemblyai(transcript)

    assert len(result.segments) == 1
    assert [w.text for w in result.words] == ["Ola", "mundo"]
    assert result.words[0].start == pytest.approx(0.0)
    assert result.words[1].end == pytest.approx(1.0)
    assert result.words[0].speaker is None


def test_build_result_com_diarizacao_um_segmento_por_utterance():
    transcript = FakeTranscript(
        utterances=[
            FakeUtterance("A", [FakeWord("Oi", 0, 300)]),
            FakeUtterance("B", [FakeWord("Fala", 300, 600), FakeWord("ai", 600, 900)]),
        ]
    )
    result = build_result_from_assemblyai(transcript)

    assert len(result.segments) == 2
    assert result.segments[0].speaker == "A"
    assert result.segments[1].speaker == "B"
    assert [w.speaker for w in result.words] == ["A", "B", "B"]


def test_build_result_word_id_sequencial_global():
    transcript = FakeTranscript(
        utterances=[
            FakeUtterance("A", [FakeWord("um", 0, 100), FakeWord("dois", 100, 200)]),
            FakeUtterance("B", [FakeWord("tres", 200, 300)]),
        ]
    )
    result = build_result_from_assemblyai(transcript)

    assert [w.id for w in result.words] == [0, 1, 2]


def test_build_result_utterance_vazia_e_ignorada():
    transcript = FakeTranscript(
        utterances=[FakeUtterance("A", []), FakeUtterance("B", [FakeWord("oi", 0, 100)])]
    )
    result = build_result_from_assemblyai(transcript)

    assert len(result.segments) == 1
    assert result.segments[0].speaker == "B"


def test_build_result_propaga_audio_path_e_language():
    transcript = FakeTranscript(words=[FakeWord("oi", 0, 100)], language_code="pt")
    result = build_result_from_assemblyai(transcript, audio_path="video.mp4")

    assert result.audio_path == "video.mp4"
    assert result.language == "pt"


# --- AssemblyAITranscriber ---------------------------------------------------------


def test_transcribe_usa_client_injetado_sem_chamada_real():
    transcript = FakeTranscript(words=[FakeWord("oi", 0, 100)])
    client = FakeClient(transcript)
    transcriber = AssemblyAITranscriber(client_factory=lambda: client, diarize=False)

    result = transcriber.transcribe("video.mp4")

    assert [w.text for w in result.words] == ["oi"]
    assert client.calls[0][0] == "video.mp4"


def test_transcribe_carrega_client_uma_vez_so():
    transcript = FakeTranscript(words=[])
    calls = []

    def factory():
        calls.append(1)
        return FakeClient(transcript)

    transcriber = AssemblyAITranscriber(client_factory=factory)
    transcriber.transcribe("a.mp4")
    transcriber.transcribe("b.mp4")

    assert len(calls) == 1


def test_transcribe_levanta_erro_quando_status_error():
    transcript = FakeTranscript(status="error", error="audio corrompido")
    client = FakeClient(transcript)
    transcriber = AssemblyAITranscriber(client_factory=lambda: client)

    with pytest.raises(TranscriptionError, match="audio corrompido"):
        transcriber.transcribe("video.mp4")


def test_transcribe_sem_api_key_e_sem_client_factory_levanta_erro(monkeypatch):
    import sys
    import types

    fake_aai = types.ModuleType("assemblyai")
    fake_aai.settings = types.SimpleNamespace(api_key=None)
    fake_aai.Transcriber = lambda: None
    monkeypatch.setitem(sys.modules, "assemblyai", fake_aai)

    transcriber = AssemblyAITranscriber(api_key=None)
    with pytest.raises(TranscriptionError, match="ASSEMBLYAI_API_KEY"):
        transcriber.transcribe("video.mp4")


def test_build_config_usa_language_code_e_diarize(monkeypatch):
    import sys
    import types

    captured = {}

    class FakeConfig:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_aai = types.ModuleType("assemblyai")
    fake_aai.TranscriptionConfig = FakeConfig
    monkeypatch.setitem(sys.modules, "assemblyai", fake_aai)

    transcriber = AssemblyAITranscriber(language_code="pt", diarize=True)
    transcriber._build_config()

    assert captured == {"language_code": "pt", "speaker_labels": True, "word_boost": []}
