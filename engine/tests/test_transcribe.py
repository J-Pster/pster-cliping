import sys
import types
from types import SimpleNamespace

import pytest

from clipador.transcribe import (
    FasterWhisperTranscriber,
    NullDiarizer,
    Segment,
    SpeakerTurn,
    TranscriptionResult,
    Word,
    apply_speaker_turns,
    build_result,
    load_transcription,
    save_transcription,
)


def _raw_word(word, start, end):
    return SimpleNamespace(word=word, start=start, end=end, probability=0.9)


def _fake_whisper_output():
    segments = [
        SimpleNamespace(
            start=0.0,
            end=1.4,
            text=" O Brasil precisa",
            words=[_raw_word(" O", 0.0, 0.2), _raw_word(" Brasil", 0.2, 0.8), _raw_word(" precisa", 0.8, 1.4)],
        ),
        SimpleNamespace(
            start=1.4,
            end=2.6,
            text=" de coragem",
            words=[_raw_word(" de", 1.4, 1.7), _raw_word(" coragem", 1.7, 2.6)],
        ),
    ]
    info = SimpleNamespace(language="pt", duration=2.6)
    return segments, info


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio_path, **kwargs):
        self.calls.append((audio_path, kwargs))
        return _fake_whisper_output()


def _sample_result():
    segments, info = _fake_whisper_output()
    return build_result(segments, info, "video.mp4")


def test_build_result_gera_ids_sequenciais_e_globais():
    result = _sample_result()

    assert [w.id for w in result.words] == [0, 1, 2, 3, 4]
    assert [w.text for w in result.words] == ["O", "Brasil", "precisa", "de", "coragem"]
    assert [s.id for s in result.segments] == [0, 1]
    assert result.language == "pt"
    assert result.duration == 2.6
    assert result.audio_path == "video.mp4"
    assert all(w.speaker is None for w in result.words)


def test_word_by_id():
    result = _sample_result()

    assert result.word_by_id(3).text == "de"
    with pytest.raises(KeyError):
        result.word_by_id(99)


def test_serializacao_em_disco_faz_round_trip(tmp_path):
    result = _sample_result()
    result.words[0].speaker = "SPEAKER_00"
    path = tmp_path / "out" / "transcricao.json"

    save_transcription(result, path)
    reloaded = load_transcription(path)

    assert reloaded.to_dict() == result.to_dict()
    assert reloaded.words[0].speaker == "SPEAKER_00"
    assert reloaded.words[1].speaker is None
    assert [w.id for w in reloaded.words] == [0, 1, 2, 3, 4]


def test_from_dict_rejeita_schema_desconhecido():
    with pytest.raises(ValueError, match="schema"):
        TranscriptionResult.from_dict({"version": 99, "segments": []})


def test_null_diarizer_mantem_speaker_none():
    result = _sample_result()

    assert NullDiarizer().assign(result, "video.mp4") is result
    assert all(w.speaker is None for w in result.words)


def test_apply_speaker_turns_atribui_speaker_dominante():
    result = TranscriptionResult(
        segments=[
            Segment(
                id=0,
                start=0.0,
                end=2.0,
                text="um dois",
                words=[Word(0, "um", 0.0, 0.9), Word(1, "dois", 1.1, 2.0)],
            ),
            Segment(
                id=1,
                start=2.0,
                end=4.0,
                text="tres",
                words=[Word(2, "tres", 2.0, 4.0)],
            ),
        ]
    )
    turns = [SpeakerTurn("SPEAKER_00", 0.0, 2.0), SpeakerTurn("SPEAKER_01", 2.0, 5.0)]

    apply_speaker_turns(result, turns)

    assert [w.speaker for w in result.words] == ["SPEAKER_00", "SPEAKER_00", "SPEAKER_01"]
    assert [s.speaker for s in result.segments] == ["SPEAKER_00", "SPEAKER_01"]


def test_apply_speaker_turns_sem_turnos_mantem_none():
    result = _sample_result()

    apply_speaker_turns(result, [])

    assert all(w.speaker is None for w in result.words)
    assert all(s.speaker is None for s in result.segments)


def test_transcriber_usa_modelo_injetado_com_word_timestamps():
    model = FakeModel()
    transcriber = FasterWhisperTranscriber(language="pt", model_factory=lambda: model)

    result = transcriber.transcribe("audio.wav")

    audio_path, kwargs = model.calls[0]
    assert audio_path == "audio.wav"
    assert kwargs["word_timestamps"] is True
    assert kwargs["language"] == "pt"
    assert len(result.words) == 5
    assert result.audio_path == "audio.wav"


def test_transcriber_carrega_modelo_uma_vez_e_so_no_primeiro_uso():
    calls = []
    transcriber = FasterWhisperTranscriber(model_factory=lambda: calls.append(1) or FakeModel())

    assert calls == []
    transcriber.transcribe("a.wav")
    transcriber.transcribe("b.wav")
    assert calls == [1]


def test_transcriber_aplica_diarizer_injetado():
    class StubDiarizer:
        def assign(self, result, audio_path):
            for word in result.words:
                word.speaker = "RENAN"
            return result

    transcriber = FasterWhisperTranscriber(
        diarizer=StubDiarizer(), model_factory=lambda: FakeModel()
    )

    result = transcriber.transcribe("audio.wav")

    assert all(w.speaker == "RENAN" for w in result.words)


def test_import_de_faster_whisper_e_lazy(monkeypatch):
    created = {}

    class StubWhisperModel:
        def __init__(self, model_size, device, compute_type):
            created["args"] = (model_size, device, compute_type)

    stub = types.ModuleType("faster_whisper")
    stub.WhisperModel = StubWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", stub)

    transcriber = FasterWhisperTranscriber(model_size="medium", device="cpu", compute_type="int8")
    assert transcriber.model is not None
    assert created["args"] == ("medium", "cpu", "int8")
