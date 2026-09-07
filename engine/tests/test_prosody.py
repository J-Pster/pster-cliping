import math
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from clipador.select.prosody import (
    AudioSignals,
    ProsodyWindow,
    extract_prosody_windows,
    format_prosody_table,
    load_audio_signals,
)
from clipador.select.selector import PROSODY_HEADER, TOOL_NAME, build_user_prompt, select_clips
from clipador.transcribe.models import Segment, TranscriptionResult, Word

AUDIO = Path("fake.wav")


def transcription_with_word_starts(starts: list[float]) -> TranscriptionResult:
    words = [
        Word(id=index, text=f"p{index}", start=start, end=start + 0.2)
        for index, start in enumerate(starts)
    ]
    if not words:
        return TranscriptionResult()
    segment = Segment(
        id=0,
        start=words[0].start,
        end=words[-1].end,
        text=" ".join(w.text for w in words),
        words=words,
    )
    return TranscriptionResult(segments=[segment], language="pt", duration=words[-1].end)


def signals(
    duration: float,
    frame_times: list[float],
    rms: list[float],
    f0: list[float],
) -> AudioSignals:
    return AudioSignals(duration=duration, frame_times=frame_times, rms=rms, f0=f0)


def analyzer_for(audio_signals: AudioSignals):
    def _analyzer(path: Path) -> AudioSignals:
        assert path == AUDIO
        return audio_signals

    return _analyzer


# --- janelamento ----------------------------------------------------------


def test_extract_prosody_windows_fatia_em_janelas_fixas_e_apara_a_ultima():
    audio = signals(12.0, [0.0, 4.0, 8.0], [0.5, 0.5, 0.5], [200.0, 200.0, 200.0])

    windows = extract_prosody_windows(
        AUDIO, TranscriptionResult(), analyzer=analyzer_for(audio)
    )

    assert [(w.start, w.end) for w in windows] == [(0.0, 5.0), (5.0, 10.0), (10.0, 12.0)]


def test_extract_prosody_windows_com_audio_vazio_retorna_lista_vazia():
    audio = signals(0.0, [], [], [])

    assert extract_prosody_windows(AUDIO, TranscriptionResult(), analyzer=analyzer_for(audio)) == []


def test_extract_prosody_windows_rejeita_janela_nao_positiva():
    audio = signals(10.0, [0.0], [0.5], [200.0])

    with pytest.raises(ValueError):
        extract_prosody_windows(
            AUDIO, TranscriptionResult(), window_seconds=0, analyzer=analyzer_for(audio)
        )


# --- energia --------------------------------------------------------------


def test_rms_energy_e_a_media_dos_frames_da_janela():
    audio = signals(10.0, [0.0, 2.0, 6.0, 8.0], [0.2, 0.6, 0.9, 0.7], [200.0] * 4)

    windows = extract_prosody_windows(
        AUDIO, TranscriptionResult(), analyzer=analyzer_for(audio)
    )

    assert windows[0].rms_energy == pytest.approx(0.4)
    assert windows[1].rms_energy == pytest.approx(0.8)


def test_janela_sem_frame_fica_com_energia_zero():
    audio = signals(10.0, [0.0, 1.0], [0.5, 0.5], [200.0, 200.0])

    windows = extract_prosody_windows(
        AUDIO, TranscriptionResult(), analyzer=analyzer_for(audio)
    )

    assert windows[1].rms_energy == 0.0


# --- pitch ----------------------------------------------------------------


def test_pitch_delta_sigma_mede_a_janela_contra_o_desvio_do_video_inteiro():
    # Pitch global: 100, 100, 300, 300 -> media 200, desvio populacional 100.
    audio = signals(10.0, [0.0, 1.0, 6.0, 7.0], [0.5] * 4, [100.0, 100.0, 300.0, 300.0])

    windows = extract_prosody_windows(
        AUDIO, TranscriptionResult(), analyzer=analyzer_for(audio)
    )

    assert windows[0].pitch_delta_sigma == pytest.approx(-1.0)
    assert windows[1].pitch_delta_sigma == pytest.approx(1.0)


def test_pitch_delta_sigma_ignora_frames_sem_voz():
    nan = math.nan
    audio = signals(10.0, [0.0, 1.0, 6.0, 7.0], [0.5] * 4, [100.0, nan, nan, 300.0])

    windows = extract_prosody_windows(
        AUDIO, TranscriptionResult(), analyzer=analyzer_for(audio)
    )

    assert windows[0].pitch_delta_sigma == pytest.approx(-1.0)
    assert windows[1].pitch_delta_sigma == pytest.approx(1.0)


def test_pitch_delta_sigma_zera_quando_a_janela_nao_tem_voz():
    audio = signals(10.0, [0.0, 6.0], [0.5, 0.5], [200.0, math.nan])

    windows = extract_prosody_windows(
        AUDIO, TranscriptionResult(), analyzer=analyzer_for(audio)
    )

    assert windows[1].pitch_delta_sigma == 0.0


def test_pitch_delta_sigma_zera_quando_o_video_inteiro_tem_pitch_constante():
    audio = signals(10.0, [0.0, 6.0], [0.5, 0.5], [200.0, 200.0])

    windows = extract_prosody_windows(
        AUDIO, TranscriptionResult(), analyzer=analyzer_for(audio)
    )

    assert [w.pitch_delta_sigma for w in windows] == [0.0, 0.0]


# --- ritmo de fala --------------------------------------------------------


def test_speech_rate_conta_palavras_da_transcricao_dentro_da_janela():
    audio = signals(10.0, [0.0, 6.0], [0.5, 0.5], [200.0, 200.0])
    # 10 palavras na primeira janela, 2 na segunda.
    starts = [index * 0.5 for index in range(10)] + [5.5, 6.5]

    windows = extract_prosody_windows(
        AUDIO, transcription_with_word_starts(starts), analyzer=analyzer_for(audio)
    )

    assert windows[0].speech_rate == pytest.approx(2.0)
    assert windows[1].speech_rate == pytest.approx(0.4)


def test_speech_rate_inclui_palavra_no_limite_final_da_ultima_janela():
    audio = signals(6.0, [0.0], [0.5], [200.0])

    windows = extract_prosody_windows(
        AUDIO, transcription_with_word_starts([6.0]), analyzer=analyzer_for(audio)
    )

    assert windows[-1].speech_rate == pytest.approx(1.0)


# --- formatacao da tabela -------------------------------------------------


def test_format_prosody_table_produz_uma_linha_por_janela():
    windows = [
        ProsodyWindow(
            start=120.0, end=125.0, rms_energy=0.82, pitch_delta_sigma=1.4, speech_rate=4.1
        ),
        ProsodyWindow(
            start=125.0, end=130.0, rms_energy=0.31, pitch_delta_sigma=-0.92, speech_rate=2.0
        ),
    ]

    assert format_prosody_table(windows) == (
        "t=120-125 | energia 0.82 | pitch_delta +1.4s | fala 4.1 pps\n"
        "t=125-130 | energia 0.31 | pitch_delta -0.9s | fala 2.0 pps"
    )


def test_format_prosody_table_sem_janelas_e_string_vazia():
    assert format_prosody_table([]) == ""


# --- injecao no prompt de selecao -----------------------------------------


class FakeToolUseBlock:
    def __init__(self, name: str, payload: dict):
        self.type = "tool_use"
        self.name = name
        self.input = payload


class FakeMessages:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class FakeResponse:
    def __init__(self, content: list):
        self.content = content


class FakeClient:
    def __init__(self):
        self.messages = FakeMessages(
            FakeResponse([FakeToolUseBlock(TOOL_NAME, {"candidates": []})])
        )


def build_kb():
    from clipador.kb.knowledge import KnowledgeBase, KnowledgeDocument

    return KnowledgeBase(
        movement="Movimento Exemplo",
        core=[KnowledgeDocument(name="pautas", title="Pautas", content="Pauta de exemplo.")],
        topics_dir=None,
    )


def test_build_user_prompt_sem_prosodia_permanece_igual():
    transcription = transcription_with_word_starts([0.0, 1.0])

    assert build_user_prompt(transcription, 3) == build_user_prompt(transcription, 3, None)


def test_build_user_prompt_injeta_a_prosodia_antes_da_transcricao():
    transcription = transcription_with_word_starts([0.0, 1.0])
    table = "t=0-5 | energia 0.82 | pitch_delta +1.4s | fala 4.1 pps"

    prompt = build_user_prompt(transcription, 3, table)

    assert prompt.index(table) < prompt.index("Transcricao com timestamp por palavra")
    assert PROSODY_HEADER in prompt


def test_select_clips_repassa_a_tabela_de_prosodia_para_o_prompt():
    client = FakeClient()
    table = "t=0-5 | energia 0.82 | pitch_delta +1.4s | fala 4.1 pps"

    select_clips(
        transcription_with_word_starts([0.0, 1.0]),
        build_kb(),
        client=client,
        prosody_table=table,
    )
    prompt = client.messages.calls[0]["messages"][0]["content"]

    assert table in prompt
    assert "nao e transcricao" in prompt


def test_select_clips_sem_prosodia_nao_menciona_prosodia():
    client = FakeClient()

    select_clips(transcription_with_word_starts([0.0, 1.0]), build_kb(), client=client)

    assert "prosodia" not in client.messages.calls[0]["messages"][0]["content"]


# --- caminho real do librosa (stubado) ------------------------------------


def install_librosa_stub(monkeypatch, samples: np.ndarray, sample_rate: int) -> dict:
    recorded: dict = {}

    def load(path, sr=None, mono=True):
        recorded["load"] = {"path": path, "sr": sr, "mono": mono}
        return samples, sample_rate

    def rms(y, frame_length, hop_length):
        frames = 1 + len(y) // hop_length
        return np.array([np.linspace(0.1, 0.9, frames)])

    def pyin(y, fmin, fmax, sr, frame_length, hop_length):
        recorded["pyin"] = {"fmin": fmin, "fmax": fmax, "sr": sr}
        frames = 1 + len(y) // hop_length
        f0 = np.full(frames, 200.0)
        f0[0] = np.nan
        return f0, np.ones(frames, dtype=bool), np.ones(frames)

    module = types.ModuleType("librosa")
    module.load = load
    module.pyin = pyin
    module.feature = types.SimpleNamespace(rms=rms)
    monkeypatch.setitem(sys.modules, "librosa", module)
    return recorded


def test_load_audio_signals_usa_librosa_e_devolve_floats_puros(monkeypatch):
    sample_rate = 16000
    samples = np.zeros(sample_rate * 2, dtype=np.float32)
    recorded = install_librosa_stub(monkeypatch, samples, sample_rate)

    result = load_audio_signals(AUDIO)

    assert recorded["load"] == {"path": "fake.wav", "sr": None, "mono": True}
    assert recorded["pyin"]["sr"] == sample_rate
    assert result.duration == pytest.approx(2.0)
    assert len(result.frame_times) == len(result.rms) == len(result.f0)
    assert result.frame_times[1] == pytest.approx(512 / sample_rate)
    assert all(isinstance(value, float) for value in result.rms)
    assert math.isnan(result.f0[0])


def test_extract_prosody_windows_usa_librosa_quando_nao_recebe_analyzer(monkeypatch):
    sample_rate = 16000
    install_librosa_stub(monkeypatch, np.zeros(sample_rate * 12, dtype=np.float32), sample_rate)

    windows = extract_prosody_windows(AUDIO, transcription_with_word_starts([0.0, 1.0, 7.0]))

    assert [(w.start, w.end) for w in windows] == [(0.0, 5.0), (5.0, 10.0), (10.0, 12.0)]
    assert windows[0].speech_rate == pytest.approx(0.4)
    assert windows[0].rms_energy > 0
