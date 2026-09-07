"""Sinais de prosódia programáticos (energia, pitch, ritmo de fala) anexados ao prompt de seleção.

A transcrição diz o QUE foi falado; a prosódia diz COMO foi falado. Injetar energia RMS,
desvio de pitch e palavras por segundo dá ao LLM evidência de ênfase e ativação emocional
que o texto puro não carrega, por um custo de tokens irrisório.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, pstdev

from clipador.transcribe.models import TranscriptionResult

DEFAULT_WINDOW_SECONDS = 5.0

# Faixa de F0 da voz humana falada, de C2 a C7.
PITCH_FMIN_HZ = 65.0
PITCH_FMAX_HZ = 2093.0

HOP_LENGTH = 512
FRAME_LENGTH = 2048


@dataclass(frozen=True)
class AudioSignals:
    """Séries temporais cruas extraídas do áudio, já convertidas para float puro.

    `f0` usa NaN nos frames sem voz detectada, que é o que o pyin devolve.
    """

    duration: float
    frame_times: list[float]
    rms: list[float]
    f0: list[float]


@dataclass(frozen=True)
class ProsodyWindow:
    start: float
    end: float
    rms_energy: float
    pitch_delta_sigma: float
    speech_rate: float


AudioAnalyzer = Callable[[Path], AudioSignals]


def load_audio_signals(audio_path: Path) -> AudioSignals:
    """Extração real via librosa. Import lazy: librosa só é exigido quando a prosódia é usada."""
    import librosa

    y, sample_rate = librosa.load(str(audio_path), sr=None, mono=True)

    rms = librosa.feature.rms(y=y, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
    f0, _voiced_flag, _voiced_prob = librosa.pyin(
        y=y,
        fmin=PITCH_FMIN_HZ,
        fmax=PITCH_FMAX_HZ,
        sr=sample_rate,
        frame_length=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
    )

    frame_count = min(len(rms), len(f0))
    return AudioSignals(
        duration=len(y) / float(sample_rate),
        frame_times=[index * HOP_LENGTH / float(sample_rate) for index in range(frame_count)],
        rms=[float(value) for value in rms[:frame_count]],
        f0=[float(value) for value in f0[:frame_count]],
    )


def extract_prosody_windows(
    audio_path: Path,
    transcription: TranscriptionResult,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    analyzer: AudioAnalyzer | None = None,
) -> list[ProsodyWindow]:
    """Fatia o áudio em janelas fixas e mede energia, desvio de pitch e ritmo de fala em cada uma.

    `analyzer` existe para testar sem librosa e sem áudio real.
    """
    if window_seconds <= 0:
        raise ValueError("window_seconds precisa ser positivo")

    signals = (analyzer or load_audio_signals)(audio_path)
    if signals.duration <= 0:
        return []

    voiced = [value for value in signals.f0 if not math.isnan(value)]
    global_mean = fmean(voiced) if voiced else 0.0
    global_sigma = pstdev(voiced) if len(voiced) > 1 else 0.0

    words = transcription.words
    windows: list[ProsodyWindow] = []
    for start, end in _window_bounds(signals.duration, window_seconds):
        include_end = end >= signals.duration
        frames = [
            index
            for index, moment in enumerate(signals.frame_times)
            if _inside(moment, start, end, include_end)
        ]
        window_voiced = [
            signals.f0[index] for index in frames if not math.isnan(signals.f0[index])
        ]
        word_count = sum(1 for word in words if _inside(word.start, start, end, include_end))

        windows.append(
            ProsodyWindow(
                start=start,
                end=end,
                rms_energy=fmean(signals.rms[index] for index in frames) if frames else 0.0,
                pitch_delta_sigma=(
                    (fmean(window_voiced) - global_mean) / global_sigma
                    if window_voiced and global_sigma > 0
                    else 0.0
                ),
                speech_rate=word_count / (end - start) if end > start else 0.0,
            )
        )
    return windows


def format_prosody_table(windows: Sequence[ProsodyWindow]) -> str:
    """Uma linha por janela, compacta o bastante para caber no prompt sem competir com a transcrição."""
    return "\n".join(
        f"t={window.start:.0f}-{window.end:.0f} "
        f"| energia {window.rms_energy:.2f} "
        f"| pitch_delta {window.pitch_delta_sigma:+.1f}s "
        f"| fala {window.speech_rate:.1f} pps"
        for window in windows
    )


def _window_bounds(duration: float, window_seconds: float) -> list[tuple[float, float]]:
    bounds: list[tuple[float, float]] = []
    start = 0.0
    while start < duration:
        bounds.append((start, min(start + window_seconds, duration)))
        start += window_seconds
    return bounds


def _inside(moment: float, start: float, end: float, include_end: bool) -> bool:
    return start <= moment < end or (include_end and moment == end)
