"""Testes do WhisperXTranscriber, 100% offline: o módulo `whisperx` é sempre stubado.

Os dicts abaixo reproduzem o formato real da lib:
- `model.transcribe()` devolve {"segments": [{start, end, text}], "language": "pt"} (sem words)
- `whisperx.align()` devolve {"segments": [{start, end, text, words: [{word, start, end, score}]}],
  "word_segments": [...]}
- `whisperx.assign_word_speakers()` devolve o mesmo dict com "speaker" em segments e words
- `DiarizationPipeline(audio)` devolve um DataFrame pandas (aqui, um objeto opaco qualquer)
"""

import sys
import types

import pytest

from clipador.transcribe import WhisperXTranscriber, build_result_from_whisperx


def _raw_transcribe_output():
    return {
        "segments": [
            {"start": 0.0, "end": 1.4, "text": " O Brasil precisa"},
            {"start": 1.4, "end": 2.6, "text": " de coragem"},
        ],
        "language": "pt",
    }


def _aligned_output():
    return {
        "segments": [
            {
                "start": 0.0,
                "end": 1.4,
                "text": " O Brasil precisa",
                "words": [
                    {"word": "O", "start": 0.0, "end": 0.18, "score": 0.91},
                    {"word": "Brasil", "start": 0.22, "end": 0.79, "score": 0.88},
                    {"word": "precisa", "start": 0.83, "end": 1.4, "score": 0.93},
                ],
            },
            {
                "start": 1.4,
                "end": 2.6,
                "text": " de coragem",
                "words": [
                    {"word": "de", "start": 1.42, "end": 1.68, "score": 0.9},
                    {"word": "coragem", "start": 1.72, "end": 2.6, "score": 0.95},
                ],
            },
        ],
        "word_segments": [],
    }


def _diarized_output():
    result = _aligned_output()
    speakers = ["SPEAKER_00", "SPEAKER_00", "SPEAKER_00", "SPEAKER_01", "SPEAKER_01"]
    flat = [w for s in result["segments"] for w in s["words"]]
    for word, speaker in zip(flat, speakers):
        word["speaker"] = speaker
    result["segments"][0]["speaker"] = "SPEAKER_00"
    result["segments"][1]["speaker"] = "SPEAKER_01"
    return result


class FakeAsrModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return _raw_transcribe_output()


@pytest.fixture
def whisperx_stub(monkeypatch):
    """Instala um módulo `whisperx` falso em sys.modules e registra as chamadas feitas."""
    calls = {
        "load_model": [],
        "asr_options": [],
        "load_align_model": [],
        "align": [],
        "diarize": [],
        "assign": [],
    }

    class StubDiarizationPipeline:
        def __init__(self, token=None, device=None):
            calls["diarize"].append({"token": token, "device": device})

        def __call__(self, audio):
            return "diarize-segments-dataframe"

    def load_model(model_size, device, compute_type=None, language=None, asr_options=None):
        calls["load_model"].append((model_size, device, compute_type, language))
        calls["asr_options"].append(asr_options)
        return FakeAsrModel()

    def load_align_model(language_code=None, device=None):
        calls["load_align_model"].append((language_code, device))
        return "align-model", {"language": language_code}

    def align(segments, model, metadata, audio, device, return_char_alignments=False):
        calls["align"].append(
            {
                "segments": segments,
                "model": model,
                "metadata": metadata,
                "audio": audio,
                "device": device,
                "return_char_alignments": return_char_alignments,
            }
        )
        return _aligned_output()

    def assign_word_speakers(diarize_segments, aligned):
        calls["assign"].append((diarize_segments, aligned))
        return _diarized_output()

    module = types.ModuleType("whisperx")
    module.load_model = load_model
    module.load_audio = lambda path: f"waveform:{path}"
    module.load_align_model = load_align_model
    module.align = align
    module.assign_word_speakers = assign_word_speakers
    diarize_module = types.ModuleType("whisperx.diarize")
    diarize_module.DiarizationPipeline = StubDiarizationPipeline
    module.diarize = diarize_module

    monkeypatch.setitem(sys.modules, "whisperx", module)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", diarize_module)
    return calls


def test_transcricao_basica_sem_diarizacao(whisperx_stub):
    transcriber = WhisperXTranscriber(device="cpu")

    result = transcriber.transcribe("audio.wav")

    assert [w.text for w in result.words] == ["O", "Brasil", "precisa", "de", "coragem"]
    assert [w.id for w in result.words] == [0, 1, 2, 3, 4]
    assert [s.id for s in result.segments] == [0, 1]
    assert result.language == "pt"
    assert result.duration == 2.6
    assert result.audio_path == "audio.wav"
    assert all(w.speaker is None for w in result.words)
    assert whisperx_stub["diarize"] == []


def test_fluxo_passa_audio_carregado_e_idioma_detectado_para_o_alinhamento(whisperx_stub):
    transcriber = WhisperXTranscriber(device="cpu", language="pt")

    transcriber.transcribe("video.mp4")

    align_call = whisperx_stub["align"][0]
    assert align_call["audio"] == "waveform:video.mp4"
    assert align_call["device"] == "cpu"
    assert align_call["return_char_alignments"] is False
    assert align_call["segments"] == _raw_transcribe_output()["segments"]
    assert whisperx_stub["load_align_model"] == [("pt", "cpu")]


def test_diarizacao_real_com_hf_token(whisperx_stub):
    transcriber = WhisperXTranscriber(device="cpu", diarize=True, hf_token="hf_fake_token")

    result = transcriber.transcribe("audio.wav")

    assert whisperx_stub["diarize"] == [{"token": "hf_fake_token", "device": "cpu"}]
    assert whisperx_stub["assign"][0][0] == "diarize-segments-dataframe"
    assert [w.speaker for w in result.words] == [
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_01",
        "SPEAKER_01",
    ]
    assert [s.speaker for s in result.segments] == ["SPEAKER_00", "SPEAKER_01"]


def test_diarize_sem_hf_token_avisa_e_cai_para_null_diarizer(whisperx_stub):
    transcriber = WhisperXTranscriber(device="cpu", diarize=True)

    with pytest.warns(RuntimeWarning, match="hf_token"):
        result = transcriber.transcribe("audio.wav")

    assert whisperx_stub["diarize"] == []
    assert len(result.words) == 5
    assert all(w.speaker is None for w in result.words)


def test_diarizer_injetado_e_aplicado_quando_whisperx_nao_diariza(whisperx_stub):
    class StubDiarizer:
        def assign(self, result, audio_path):
            for word in result.words:
                word.speaker = "RENAN"
            return result

    transcriber = WhisperXTranscriber(device="cpu", diarizer=StubDiarizer())

    result = transcriber.transcribe("audio.wav")

    assert all(w.speaker == "RENAN" for w in result.words)


def test_model_factory_carrega_uma_vez_e_so_no_primeiro_uso(whisperx_stub):
    calls = []

    def factory():
        calls.append(1)
        return FakeAsrModel()

    transcriber = WhisperXTranscriber(device="cpu", model_factory=factory)

    assert calls == []
    transcriber.transcribe("a.wav")
    transcriber.transcribe("b.wav")
    assert calls == [1]
    assert whisperx_stub["load_model"] == []
    assert len(whisperx_stub["load_align_model"]) == 1


def test_load_model_default_usa_parametros_do_construtor(whisperx_stub):
    transcriber = WhisperXTranscriber(
        model_size="medium", device="cuda", compute_type="float16", language="pt"
    )

    transcriber.transcribe("audio.wav")

    assert whisperx_stub["load_model"] == [("medium", "cuda", "float16", "pt")]


def test_import_de_whisperx_e_lazy(monkeypatch):
    monkeypatch.delitem(sys.modules, "whisperx", raising=False)

    transcriber = WhisperXTranscriber()

    assert transcriber.diarize is False
    assert "whisperx" not in sys.modules


def test_palavra_sem_timestamp_do_ctc_usa_o_cursor_anterior():
    # Números e símbolos voltam do alinhamento CTC sem start/end.
    segments = [
        {
            "start": 0.0,
            "end": 2.0,
            "text": "meta 2026 agora",
            "words": [
                {"word": "meta", "start": 0.0, "end": 0.5, "score": 0.9},
                {"word": "2026"},
                {"word": "agora", "start": 1.2, "end": 2.0, "score": 0.9},
            ],
        }
    ]

    result = build_result_from_whisperx(segments, language="pt", audio_path="a.wav")

    # A normalizacao garante duracao minima por palavra: o "2026" veio do CTC com
    # start == end (sem fonema alinhavel) e sairia com `\k0`, invisivel no karaoke.
    assert [(w.text, round(w.start, 2), round(w.end, 2)) for w in result.words] == [
        ("meta", 0.0, 0.5),
        ("2026", 0.5, 0.58),
        ("agora", 1.2, 2.0),
    ]
    assert [w.id for w in result.words] == [0, 1, 2]
