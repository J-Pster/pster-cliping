import sys
import types
from types import SimpleNamespace

import numpy as np
import pytest

from clipador.reframe import (
    CropKeyframe,
    CropWindow,
    CropWindowCalculator,
    FaceBox,
    LargestFaceHeuristic,
    MediaPipeFaceDetector,
    OpenCvFrameSampler,
    PySceneDetector,
    ReframeError,
    ReframePlan,
    Scene,
    VerticalReframer,
    build_crop_filter,
    build_scenes,
    faces_from_mediapipe,
    sample_frame_indices,
    sample_times,
)
from clipador.reframe.reframer import MAX_EXPRESSION_KEYFRAMES_TOTAL, _decimate_keyframes

FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080


def _face(center_x, width=200.0, height=200.0, confidence=0.9, center_y=540.0):
    return FaceBox(
        x=center_x - width / 2,
        y=center_y - height / 2,
        width=width,
        height=height,
        confidence=confidence,
    )


def _calculator(smoothing=0.25):
    return CropWindowCalculator(FRAME_WIDTH, FRAME_HEIGHT, smoothing=smoothing)


# --- FaceBox / Scene -------------------------------------------------------


def test_facebox_expoe_centro_e_area():
    face = FaceBox(x=100.0, y=200.0, width=50.0, height=80.0)

    assert face.center == (125.0, 240.0)
    assert face.area == 4000.0


def test_scene_expoe_duracao_e_contagem_de_frames():
    scene = Scene(index=0, start_frame=30, end_frame=120, start_time=1.0, end_time=4.0)

    assert scene.frame_count == 90
    assert scene.duration == 3.0


# --- CropWindowCalculator --------------------------------------------------


def test_janela_9_16_cabe_no_frame_e_tem_dimensoes_pares():
    width, height = _calculator().window_size()

    assert (width, height) == (608, 1080)
    assert width % 2 == 0 and height % 2 == 0
    assert abs(width / height - 9 / 16) < 0.01


def test_janela_mais_alta_que_o_frame_encolhe_pela_largura():
    width, height = CropWindowCalculator(480, 1920).window_size()

    assert (width, height) == (480, 852)


def test_janela_e_centrada_no_rosto_e_presa_nas_bordas():
    calculator = _calculator()

    assert calculator.window_for(960.0, 540.0) == CropWindow(x=656, y=0, width=608, height=1080)
    assert calculator.window_for(0.0, 540.0).x == 0
    assert calculator.window_for(1920.0, 540.0).x == FRAME_WIDTH - 608


def test_suavizacao_reduz_pulos_bruscos_entre_amostras():
    faces = [_face(500.0), _face(500.0), _face(1400.0), _face(1400.0), _face(1400.0)]
    calculator = _calculator(smoothing=0.25)

    suave = [w.x for w in calculator.calculate(faces)]
    cru = [w.x for w in _calculator(smoothing=1.0).calculate(faces)]

    maior_pulo_suave = max(abs(b - a) for a, b in zip(suave, suave[1:]))
    maior_pulo_cru = max(abs(b - a) for a, b in zip(cru, cru[1:]))

    assert maior_pulo_cru == 900
    assert maior_pulo_suave < maior_pulo_cru / 3
    assert suave[-1] > suave[0]


def test_smoothing_1_segue_o_rosto_sem_amortecer():
    faces = [_face(500.0), _face(1400.0)]

    windows = _calculator(smoothing=1.0).calculate(faces)

    assert [w.x for w in windows] == [500 - 304, 1400 - 304]


def test_amostra_sem_rosto_herda_o_ultimo_centro_conhecido():
    faces = [None, _face(1400.0), None]

    windows = _calculator(smoothing=1.0).calculate(faces)

    assert windows[0].x == 960 - 304
    assert windows[1].x == windows[2].x == 1400 - 304


def test_calculator_rejeita_parametros_invalidos():
    with pytest.raises(ValueError):
        CropWindowCalculator(0, 1080)
    with pytest.raises(ValueError):
        CropWindowCalculator(1920, 1080, smoothing=0.0)


# --- ActiveSpeakerDetector -------------------------------------------------


def test_heuristica_escolhe_o_maior_rosto_entre_varios():
    pequeno = _face(300.0, width=80.0, height=80.0)
    grande = _face(1500.0, width=260.0, height=260.0)

    escolhido = LargestFaceHeuristic().select_active_face([pequeno, grande, pequeno])

    assert escolhido is grande


def test_heuristica_com_um_rosto_usa_ele_e_sem_rosto_devolve_none():
    unico = _face(300.0)

    assert LargestFaceHeuristic().select_active_face([unico]) is unico
    assert LargestFaceHeuristic().select_active_face([]) is None


def test_heuristica_descarta_rostos_abaixo_da_confianca_minima():
    incerto = _face(300.0, width=400.0, height=400.0, confidence=0.2)
    confiavel = _face(1500.0, width=100.0, height=100.0, confidence=0.95)

    detector = LargestFaceHeuristic(min_confidence=0.5)

    assert detector.select_active_face([incerto, confiavel]) is confiavel
    assert detector.select_active_face([incerto]) is None


# --- Scene detection -------------------------------------------------------


class FakeTimecode:
    def __init__(self, frames, seconds):
        self._frames = frames
        self._seconds = seconds

    def get_frames(self):
        return self._frames

    def get_seconds(self):
        return self._seconds


def test_build_scenes_converte_timecodes_do_scenedetect():
    raw = [
        (FakeTimecode(0, 0.0), FakeTimecode(300, 10.0)),
        (FakeTimecode(300, 10.0), FakeTimecode(750, 25.0)),
    ]

    scenes = build_scenes(raw)

    assert [s.index for s in scenes] == [0, 1]
    assert scenes[1] == Scene(
        index=1, start_frame=300, end_frame=750, start_time=10.0, end_time=25.0
    )


def test_pyscenedetector_usa_scenedetect_stubado_sem_a_lib_instalada(monkeypatch):
    chamadas = {}

    class StubContentDetector:
        def __init__(self, threshold, min_scene_len):
            chamadas["detector"] = (threshold, min_scene_len)

    def stub_detect(video_path, detector):
        chamadas["detect"] = (video_path, detector)
        return [(FakeTimecode(0, 0.0), FakeTimecode(120, 4.0))]

    stub = types.ModuleType("scenedetect")
    stub.ContentDetector = StubContentDetector
    stub.detect = stub_detect
    monkeypatch.setitem(sys.modules, "scenedetect", stub)

    scenes = PySceneDetector(threshold=30.0, min_scene_len=20).detect_scenes("video.mp4")

    assert chamadas["detector"] == (30.0, 20)
    assert chamadas["detect"][0] == "video.mp4"
    assert scenes == [Scene(index=0, start_frame=0, end_frame=120, start_time=0.0, end_time=4.0)]


def test_amostragem_distribui_indices_e_tempos_dentro_da_cena():
    scene = Scene(index=0, start_frame=0, end_frame=100, start_time=0.0, end_time=4.0)

    assert sample_frame_indices(scene, 2) == [25, 75]
    assert sample_times(scene, 2) == [1.0, 3.0]
    assert sample_frame_indices(scene, 0) == []


def test_amostragem_nunca_passa_do_ultimo_frame_da_cena():
    scene = Scene(index=0, start_frame=10, end_frame=13, start_time=0.0, end_time=0.1)

    assert max(sample_frame_indices(scene, 5)) <= 12


# --- MediaPipe face detection ----------------------------------------------


def _mp_detection(origin_x, origin_y, width, height, score=0.9):
    """Formato da Tasks API: bounding_box ja em pixels absolutos, nao mais relativo 0..1."""
    box = SimpleNamespace(origin_x=origin_x, origin_y=origin_y, width=width, height=height)
    return SimpleNamespace(bounding_box=box, categories=[SimpleNamespace(score=score)])


def test_faces_from_mediapipe_le_pixels_absolutos_da_tasks_api():
    detections = [_mp_detection(100, 100, 200, 150), _mp_detection(900, 0, 100, 250)]

    faces = faces_from_mediapipe(detections)

    assert faces[0] == FaceBox(x=100.0, y=100.0, width=200.0, height=150.0, confidence=0.9)
    assert faces[1].x == 900.0
    assert faces[1].width == 100.0


def test_faces_from_mediapipe_sem_deteccao_devolve_lista_vazia():
    assert faces_from_mediapipe(None) == []


def test_faces_from_mediapipe_ignora_bounding_box_com_dimensao_zero():
    assert faces_from_mediapipe([_mp_detection(0, 0, 0, 100)]) == []


def test_mediapipe_detector_usa_lib_stubada_e_converte_bgr_para_rgb(monkeypatch):
    recebidos = {}

    class StubFaceDetector:
        def detect(self, image):
            recebidos["image"] = image
            return SimpleNamespace(detections=[_mp_detection(2, 1, 4, 2)])

    def fake_image_factory(data):
        recebidos["image_data"] = data
        return data

    detector = MediaPipeFaceDetector(
        detector_factory=lambda: StubFaceDetector(),
        image_factory=fake_image_factory,
    )

    frame = np.arange(4 * 8 * 3, dtype=np.uint8).reshape(4, 8, 3)
    faces = detector.detect_faces(frame)

    assert np.array_equal(recebidos["image_data"], frame[:, :, ::-1])
    assert faces == [FaceBox(x=2.0, y=1.0, width=4.0, height=2.0, confidence=0.9)]


def test_mediapipe_detector_carrega_o_modelo_uma_vez_e_so_no_primeiro_uso():
    criados = []

    class StubDetector:
        def detect(self, image):
            return SimpleNamespace(detections=[])

    detector = MediaPipeFaceDetector(
        convert_to_rgb=False,
        detector_factory=lambda: criados.append(1) or StubDetector(),
    )
    frame = np.zeros((4, 8, 3), dtype=np.uint8)

    assert criados == []
    detector.detect_faces(frame)
    detector.detect_faces(frame)
    assert criados == [1]


def test_mediapipe_detector_sem_model_path_e_sem_factory_levanta_erro_claro():
    detector = MediaPipeFaceDetector()
    frame = np.zeros((4, 8, 3), dtype=np.uint8)

    with pytest.raises(ReframeError, match="model_path"):
        detector.detect_faces(frame)


# --- FrameSampler ----------------------------------------------------------


class FakeCapture:
    def __init__(
        self,
        width=FRAME_WIDTH,
        height=FRAME_HEIGHT,
        unreadable=(),
        frame_count=100,
        fps=25.0,
    ):
        self.props = {3: width, 4: height, 5: fps, 7: frame_count}
        self.unreadable = set(unreadable)
        self.seeks = []
        self.released = False

    def get(self, prop):
        return self.props[prop]

    def set(self, prop, value):
        self.seeks.append((prop, value))

    def read(self):
        index = self.seeks[-1][1]
        if index in self.unreadable:
            return False, None
        return True, f"frame-{index}"

    def release(self):
        self.released = True


def test_frame_sampler_le_dimensoes_e_libera_a_captura():
    capture = FakeCapture()

    sampler = OpenCvFrameSampler(capture_factory=lambda path: capture)

    assert sampler.frame_size("video.mp4") == (FRAME_WIDTH, FRAME_HEIGHT)
    assert capture.released is True


def test_frame_sampler_rejeita_video_sem_dimensoes():
    sampler = OpenCvFrameSampler(capture_factory=lambda path: FakeCapture(width=0, height=0))

    with pytest.raises(ReframeError):
        sampler.frame_size("video.mp4")


def test_frame_sampler_le_frame_count_e_fps_e_libera_a_captura():
    capture = FakeCapture(frame_count=1440, fps=30.0)
    sampler = OpenCvFrameSampler(capture_factory=lambda path: capture)

    assert sampler.frame_count_and_fps("video.mp4") == (1440, 30.0)
    assert capture.released is True


def test_frame_sampler_rejeita_video_sem_frame_count_ou_fps():
    sampler = OpenCvFrameSampler(
        capture_factory=lambda path: FakeCapture(frame_count=0, fps=0.0)
    )

    with pytest.raises(ReframeError):
        sampler.frame_count_and_fps("video.mp4")


def test_frame_sampler_faz_seek_por_indice_e_marca_frame_ilegivel_como_none():
    capture = FakeCapture(unreadable={75})
    sampler = OpenCvFrameSampler(capture_factory=lambda path: capture)

    frames = sampler.read_frames("video.mp4", [25, 75])

    assert frames == ["frame-25", None]
    assert capture.seeks == [(1, 25), (1, 75)]
    assert capture.released is True


# --- build_crop_filter -----------------------------------------------------


def _plan(scene, keyframes):
    return ReframePlan(scene=scene, keyframes=tuple(keyframes))


def test_filtro_de_crop_estatico_quando_a_janela_nao_varia():
    window = CropWindow(x=656, y=0, width=608, height=1080)
    scene = Scene(index=0, start_frame=0, end_frame=100, start_time=0.0, end_time=4.0)

    filtro = build_crop_filter([_plan(scene, [CropKeyframe(1.0, window), CropKeyframe(3.0, window)])])

    assert filtro == "crop=608:1080:656:0"


def test_filtro_de_crop_vira_expressao_no_tempo_quando_a_janela_varia():
    """O crop interpola LINEARMENTE entre keyframes (desliza continuo), nao pula de
    uma vez no boundary - o artefato visivel que motivou a mudanca."""
    scene = Scene(index=0, start_frame=0, end_frame=100, start_time=0.0, end_time=6.0)
    keyframes = [
        CropKeyframe(1.0, CropWindow(x=656, y=0, width=608, height=1080)),
        CropKeyframe(3.0, CropWindow(x=100, y=0, width=608, height=1080)),
        CropKeyframe(5.0, CropWindow(x=300, y=0, width=608, height=1080)),
    ]

    filtro = build_crop_filter([_plan(scene, keyframes)])

    assert filtro == (
        "crop=608:1080:"
        "'if(lt(t,3),(656-278*(t-1)),if(lt(t,5),(100+100*(t-3)),300))':0"
    )


def test_filtro_de_crop_sem_keyframes_falha():
    scene = Scene(index=0, start_frame=0, end_frame=100, start_time=0.0, end_time=4.0)

    with pytest.raises(ReframeError):
        build_crop_filter([_plan(scene, [])])


# --- VerticalReframer ------------------------------------------------------


class FakeSceneDetector:
    def __init__(self, scenes):
        self.scenes = scenes
        self.calls = []

    def detect_scenes(self, video_path):
        self.calls.append(video_path)
        return list(self.scenes)


class FakeFrameSampler:
    def __init__(self, size=(FRAME_WIDTH, FRAME_HEIGHT), frame_count=100, fps=25.0):
        self.size = size
        self.requested = []
        self._frame_count = frame_count
        self._fps = fps

    def frame_size(self, video_path):
        return self.size

    def frame_count_and_fps(self, video_path):
        return self._frame_count, self._fps

    def read_frames(self, video_path, frame_indices):
        self.requested.extend(frame_indices)
        return [f"frame-{index}" for index in frame_indices]


class FakeFaceDetector:
    def __init__(self, faces_by_frame):
        self.faces_by_frame = faces_by_frame

    def detect_faces(self, frame):
        return self.faces_by_frame.get(frame, [])


class FakeRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)


def _reframer(**overrides):
    scene = Scene(index=0, start_frame=0, end_frame=100, start_time=0.0, end_time=4.0)
    defaults = dict(
        scene_detector=FakeSceneDetector([scene]),
        face_detector=FakeFaceDetector(
            {"frame-25": [_face(960.0)], "frame-75": [_face(960.0)]}
        ),
        frame_sampler=FakeFrameSampler(),
        sample_interval_seconds=2.0,
        min_samples_per_scene=2,
        runner=FakeRunner(),
    )
    defaults.update(overrides)
    return VerticalReframer(**defaults), scene


def test_samples_for_scene_escala_com_a_duracao_nao_e_contagem_fixa():
    """Bug relatado: com contagem fixa por cena, um clipe longo (15min = 1 cena continua)
    amostrava tao raramente quanto um curto, e o rastreamento do rosto so 'ajustava' a
    cada varios minutos. Com intervalo fixo a densidade escala com a duracao."""
    reframer, _ = _reframer(sample_interval_seconds=1.0, min_samples_per_scene=3)
    curta = Scene(index=0, start_frame=0, end_frame=90, start_time=0.0, end_time=3.0)
    longa = Scene(index=0, start_frame=0, end_frame=900, start_time=0.0, end_time=30.0)

    assert reframer._samples_for_scene(curta) == 3  # piso: cena curta demais pro intervalo
    assert reframer._samples_for_scene(longa) == 30  # 30s / 1.0s = amostra a cada segundo


# --- decimacao de keyframes (limite do parser de expressao do ffmpeg) ------


def _kf(time: float) -> CropKeyframe:
    return CropKeyframe(time=time, window=CropWindow(x=int(time), y=0, width=100, height=100))


def test_decimate_keyframes_sem_efeito_abaixo_do_teto():
    keyframes = tuple(_kf(i) for i in range(10))

    assert _decimate_keyframes(keyframes, 20) == keyframes


def test_decimate_keyframes_respeita_o_teto_e_mantem_as_bordas():
    keyframes = tuple(_kf(i) for i in range(200))

    result = _decimate_keyframes(keyframes, 50)

    assert len(result) <= 50
    assert result[0] == keyframes[0]
    assert result[-1] == keyframes[-1]


def test_decimate_keyframes_teto_minusculo_mantem_so_as_bordas():
    keyframes = tuple(_kf(i) for i in range(50))

    assert _decimate_keyframes(keyframes, 1) == (keyframes[0], keyframes[-1])


def test_plan_respeita_o_teto_global_mesmo_com_amostragem_densa():
    """Cena longa amostrada a 2x/s nao pode gerar mais keyframes do que o parser de
    expressao do ffmpeg aguenta (~99 se(...) aninhados, medido empiricamente contra o
    ffmpeg de verdade) - ver MAX_EXPRESSION_KEYFRAMES_TOTAL."""
    scene = Scene(index=0, start_frame=0, end_frame=6000, start_time=0.0, end_time=200.0)
    reframer, _ = _reframer(
        scene_detector=FakeSceneDetector([scene]),
        sample_interval_seconds=0.5,
        min_samples_per_scene=3,
        face_detector=FakeFaceDetector({}),
    )

    plans = reframer.plan("video.mp4")

    assert len(plans) == 1
    assert len(plans[0].keyframes) <= MAX_EXPRESSION_KEYFRAMES_TOTAL
    expected_times = sample_times(scene, 400)
    assert plans[0].keyframes[0].time == pytest.approx(expected_times[0])
    assert plans[0].keyframes[-1].time == pytest.approx(expected_times[-1])


def test_plan_amostra_frames_por_cena_e_gera_keyframes_no_tempo():
    reframer, scene = _reframer()

    plans = reframer.plan("video.mp4")

    assert len(plans) == 1
    assert plans[0].scene == scene
    assert [k.time for k in plans[0].keyframes] == [1.0, 3.0]
    assert reframer.frame_sampler.requested == [25, 75]
    assert reframer.scene_detector.calls == ["video.mp4"]


def test_plan_segue_o_rosto_ativo_escolhido_pela_heuristica():
    reframer, _ = _reframer(
        face_detector=FakeFaceDetector(
            {
                "frame-25": [_face(400.0, width=100.0), _face(1500.0, width=300.0)],
                "frame-75": [_face(400.0, width=100.0), _face(1500.0, width=300.0)],
            }
        ),
        smoothing=1.0,
    )

    plans = reframer.plan("video.mp4")

    assert [k.window.x for k in plans[0].keyframes] == [1500 - 304, 1500 - 304]


def test_plan_sem_cena_detectada_usa_o_video_inteiro_como_uma_cena_so():
    """scenedetect nao acha corte em plano continuo (fala sem troca de camera) - caso real
    de clipe curto de discurso. Nao e erro: vira uma cena unica cobrindo o clipe inteiro."""
    reframer, _ = _reframer(
        scene_detector=FakeSceneDetector([]),
        frame_sampler=FakeFrameSampler(frame_count=150, fps=30.0),
    )

    plans = reframer.plan("video.mp4")

    assert len(plans) == 1
    scene = plans[0].scene
    assert scene.start_frame == 0
    assert scene.end_frame == 150
    assert scene.start_time == pytest.approx(0.0)
    assert scene.end_time == pytest.approx(5.0)


def test_plan_com_scenes_explicito_vazio_ainda_falha():
    """Fallback so vale quando NINGUEM passou `scenes` - se o chamador passou uma lista
    vazia explicitamente, isso e erro dele, nao caso de detectar sozinho."""
    reframer, _ = _reframer(scene_detector=FakeSceneDetector([{"nao": "deveria ser chamado"}]))

    with pytest.raises(ReframeError, match="Nenhuma cena"):
        reframer.plan("video.mp4", scenes=[])


def test_build_command_monta_o_comando_ffmpeg_esperado():
    reframer, _ = _reframer()
    plans = reframer.plan("video.mp4")

    command = reframer.build_command("video.mp4", "saida.mp4", plans)

    assert command == [
        "ffmpeg",
        "-y",
        "-i",
        "video.mp4",
        "-vf",
        "crop=608:1080:656:0,scale=1080:1920",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-c:a",
        "copy",
        "saida.mp4",
    ]


def test_build_command_sem_target_size_nao_adiciona_scale():
    reframer, _ = _reframer(target_size=None)
    plans = reframer.plan("video.mp4")

    command = reframer.build_command("video.mp4", "saida.mp4", plans)

    assert command[command.index("-vf") + 1] == "crop=608:1080:656:0"


def test_reframe_executa_o_runner_injetado_sem_rodar_ffmpeg_de_verdade():
    runner = FakeRunner()
    reframer, _ = _reframer(runner=runner)

    resultado = reframer.reframe("video.mp4", "saida.mp4")

    command, kwargs = runner.calls[0]
    assert len(runner.calls) == 1
    assert command[0] == "ffmpeg"
    assert kwargs == {"check": True}
    assert list(resultado.command) == command
    assert str(resultado.output_path) == "saida.mp4"
    assert len(resultado.plans) == 1


def test_reframe_aceita_cenas_ja_conhecidas_e_pula_a_deteccao():
    reframer, _ = _reframer()
    cenas = [Scene(index=0, start_frame=0, end_frame=60, start_time=0.0, end_time=2.0)]

    reframer.reframe("video.mp4", "saida.mp4", scenes=cenas)

    assert reframer.scene_detector.calls == []
