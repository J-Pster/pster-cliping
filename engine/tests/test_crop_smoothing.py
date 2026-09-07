"""Suavizacao Kalman + RTS do centro do crop, com reset nos cortes de cena."""

import random
import statistics

import pytest

from clipador.reframe.crop import (
    CropWindowCalculator,
    KalmanRtsSmoother,
    scene_reset_indices,
)
from clipador.reframe.models import FaceBox, Scene

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
CENTER_Y = 540.0


def _calculator(**kwargs):
    return CropWindowCalculator(FRAME_WIDTH, FRAME_HEIGHT, **kwargs)


def _track(values):
    return [(value, CENTER_Y) for value in values]


def _xs(centers):
    return [x for x, _ in centers]


def _face(center_x):
    return FaceBox(x=center_x - 100.0, y=CENTER_Y - 100.0, width=200.0, height=200.0)


# --- reset nos cortes de cena ----------------------------------------------


def test_sem_reset_o_filtro_arrasta_o_enquadramento_atraves_do_corte():
    track = _track([500.0] * 8 + [1400.0] * 8)

    suave = _xs(_calculator().smooth(track))

    # A ultima amostra antes do corte ja foi puxada em direcao ao plano seguinte,
    # e a primeira depois do corte ainda nao chegou la: o arrasto classico.
    assert suave[7] - 500.0 > 200.0
    assert 1400.0 - suave[8] > 200.0


def test_reset_de_cena_faz_o_enquadramento_saltar_limpo_no_corte():
    track = _track([500.0] * 8 + [1400.0] * 8)

    suave = _xs(_calculator().smooth(track, reset_indices=[8]))

    assert max(abs(value - 500.0) for value in suave[:8]) < 1e-6
    assert max(abs(value - 1400.0) for value in suave[8:]) < 1e-6


def test_reset_de_cena_isola_o_ruido_de_cada_plano():
    rng = random.Random(11)
    primeira = [400.0 + rng.gauss(0, 10) for _ in range(20)]
    segunda = [1500.0 + rng.gauss(0, 10) for _ in range(20)]

    suave = _xs(_calculator().smooth(_track(primeira + segunda), reset_indices=[20]))

    assert all(value < 700.0 for value in suave[:20])
    assert all(value > 1200.0 for value in suave[20:])


def test_calculate_aceita_reset_de_cena():
    faces = [_face(500.0)] * 6 + [_face(1400.0)] * 6

    windows = _calculator().calculate(faces, reset_indices=[6])

    assert windows[5].x == 500 - 304
    assert windows[6].x == 1400 - 304


def test_scene_reset_indices_marca_a_primeira_amostra_de_cada_cena():
    scenes = [
        Scene(index=0, start_frame=0, end_frame=30, start_time=0.0, end_time=1.0),
        Scene(index=1, start_frame=30, end_frame=60, start_time=1.0, end_time=2.0),
        Scene(index=2, start_frame=60, end_frame=90, start_time=2.0, end_time=3.0),
    ]
    times = [0.1, 0.5, 0.9, 1.2, 1.6, 2.4, 2.8]

    assert scene_reset_indices(scenes, times) == [3, 5]
    assert scene_reset_indices(scenes[:1], times) == []


# --- ruido e ausencia de lag ------------------------------------------------


def test_suavizacao_reduz_a_variancia_do_ruido():
    rng = random.Random(7)
    ruidoso = [960.0 + rng.gauss(0, 25) for _ in range(60)]

    suave = _xs(_calculator().smooth(_track(ruidoso)))

    assert statistics.pvariance(suave) < statistics.pvariance(ruidoso) / 3


def test_camera_parada_converge_no_centro_real_sem_vies():
    rng = random.Random(3)
    ruidoso = [960.0 + rng.gauss(0, 20) for _ in range(200)]

    suave = _xs(_calculator().smooth(_track(ruidoso)))

    assert abs(statistics.fmean(suave[20:180]) - 960.0) < 5.0


def test_kalman_rts_nao_tem_lag_sistematico_em_movimento_continuo():
    rampa = [500.0 + 30.0 * i for i in range(40)]
    miolo = slice(10, 30)
    esperado = statistics.fmean(rampa[miolo])

    kalman = _xs(_calculator().smooth(_track(rampa)))
    ema = _xs(_calculator(smoothing_strategy="ema").smooth(_track(rampa)))

    lag_kalman = esperado - statistics.fmean(kalman[miolo])
    lag_ema = esperado - statistics.fmean(ema[miolo])

    assert abs(lag_kalman) < 1.0
    assert lag_ema > 50.0


# --- compatibilidade --------------------------------------------------------


def test_smoothing_1_reproduz_a_trajetoria_crua():
    track = _track([500.0, 700.0, 1400.0, 200.0])

    assert _xs(_calculator(smoothing=1.0).smooth(track)) == [500.0, 700.0, 1400.0, 200.0]


def test_estrategia_ema_preserva_a_media_movel_exponencial():
    track = _track([0.0, 100.0, 100.0])

    suave = _xs(_calculator(smoothing=0.5, smoothing_strategy="ema").smooth(track))

    assert suave == [0.0, 50.0, 75.0]


def test_sequencias_curtas_passam_intactas():
    smoother = KalmanRtsSmoother.from_alpha(0.25)

    assert smoother.smooth([]) == []
    assert smoother.smooth([42.0]) == [42.0]


def test_estrategia_desconhecida_e_rejeitada():
    with pytest.raises(ValueError):
        _calculator(smoothing_strategy="butterworth")
