import math
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from clipador.reframe import FaceBox
from clipador.thumbnail import (
    ExpressionScore,
    FaceLandmarkerScorer,
    FaceQualityScorer,
    IFrameExtractor,
    ScoredFrame,
    SharpnessScorer,
    ThumbnailCandidateRanker,
    ThumbnailError,
    score_sharpness,
)

# --- IFrameExtractor --------------------------------------------------------


def test_build_command_monta_flags_do_ffmpeg_para_o_trecho():
    extractor = IFrameExtractor(ffmpeg_binary="ffmpeg")

    command = extractor.build_command(
        "video.mp4", "out/candidate_%03d.jpg", start=10.5, end=15.0
    )

    assert command[0] == "ffmpeg"
    assert command[command.index("-ss") + 1] == "10.5"
    assert command[command.index("-i") + 1] == "video.mp4"
    assert command[command.index("-t") + 1] == "4.5"
    assert r"select=eq(pict_type\,I)" in command
    assert command[-1] == "out/candidate_%03d.jpg"


def test_build_command_sem_start_nem_end_omite_flags_de_recorte():
    extractor = IFrameExtractor()

    command = extractor.build_command("video.mp4", "out/candidate_%03d.jpg")

    assert "-ss" not in command
    assert "-t" not in command


def test_extract_chama_runner_injetado_e_lista_arquivos_gerados(tmp_path):
    chamados = {}

    def fake_runner(command, check):
        chamados["command"] = command
        chamados["check"] = check
        for i in range(1, 4):
            (tmp_path / f"candidate_{i:03d}.jpg").write_bytes(b"fake")

    extractor = IFrameExtractor(runner=fake_runner)

    result = extractor.extract("video.mp4", tmp_path, start=0, end=5)

    assert chamados["check"] is True
    assert chamados["command"][0] == "ffmpeg"
    assert "-ss" in chamados["command"]
    assert len(result) == 3
    assert result == sorted(tmp_path.glob("candidate_*.jpg"))


def test_extract_sem_arquivos_gerados_devolve_lista_vazia(tmp_path):
    extractor = IFrameExtractor(runner=lambda command, check: None)

    result = extractor.extract("video.mp4", tmp_path)

    assert result == []


# --- SharpnessScorer ---------------------------------------------------------


def _numpy_laplacian(gray: np.ndarray) -> np.ndarray:
    padded = np.pad(gray.astype(np.float64), 1, mode="edge")
    center = padded[1:-1, 1:-1]
    up = padded[:-2, 1:-1]
    down = padded[2:, 1:-1]
    left = padded[1:-1, :-2]
    right = padded[1:-1, 2:]
    return up + down + left + right - 4 * center


def test_score_sharpness_usa_cv2_stubado_e_diferencia_nitido_de_borrado(monkeypatch):
    stub = types.ModuleType("cv2")
    stub.CV_64F = 6
    stub.COLOR_BGR2GRAY = 7
    stub.cvtColor = staticmethod(lambda frame, code: frame.mean(axis=2))
    stub.Laplacian = staticmethod(lambda gray, ddepth: _numpy_laplacian(gray))
    monkeypatch.setitem(sys.modules, "cv2", stub)

    checker = (np.indices((8, 8)).sum(axis=0) % 2) * 255
    sharp_frame = np.stack([checker] * 3, axis=-1).astype(np.float64)
    blurry_frame = np.full((8, 8, 3), 128.0)

    scorer = SharpnessScorer()

    assert scorer.score(sharp_frame) > scorer.score(blurry_frame)
    assert scorer.score(blurry_frame) == pytest.approx(0.0)


def test_score_sharpness_aceita_funcao_de_calculo_injetada_sem_cv2():
    calc = lambda frame: float(np.var(frame))  # noqa: E731

    sharp_frame = np.array([[0.0, 255.0], [255.0, 0.0]])
    uniform_frame = np.full((2, 2), 100.0)

    assert score_sharpness(sharp_frame, calc) > score_sharpness(uniform_frame, calc)
    assert score_sharpness(uniform_frame, calc) == pytest.approx(0.0)


# --- FaceQualityScorer --------------------------------------------------------


class FakeFaceDetector:
    def __init__(self, faces):
        self._faces = faces

    def detect_faces(self, frame):
        return self._faces


def test_face_quality_sem_rosto_score_zero():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    scorer = FaceQualityScorer(face_detector=FakeFaceDetector([]))

    assert scorer.score(frame) == 0.0


def test_face_quality_rosto_centralizado_pontua_mais_que_na_borda():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    centered = FaceBox(x=40, y=40, width=20, height=20, confidence=1.0)
    edge = FaceBox(x=0, y=0, width=20, height=20, confidence=1.0)

    centered_score = FaceQualityScorer(face_detector=FakeFaceDetector([centered])).score(frame)
    edge_score = FaceQualityScorer(face_detector=FakeFaceDetector([edge])).score(frame)

    assert centered_score == pytest.approx(1.0)
    assert centered_score > edge_score


def test_face_quality_com_varios_rostos_usa_o_maior():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    small_centered = FaceBox(x=45, y=45, width=10, height=10, confidence=1.0)
    big_offcenter = FaceBox(x=0, y=0, width=40, height=40, confidence=1.0)

    scorer = FaceQualityScorer(face_detector=FakeFaceDetector([small_centered, big_offcenter]))

    assert scorer.score(frame) < 1.0


# --- FaceLandmarkerScorer ------------------------------------------------------


class FakeCategory:
    def __init__(self, category_name, score):
        self.category_name = category_name
        self.score = score


class FakeLandmarkerResult:
    def __init__(self, blendshapes=None, matrices=None):
        self.face_blendshapes = blendshapes
        self.facial_transformation_matrixes = matrices


class FakeLandmarker:
    def __init__(self, result):
        self._result = result

    def detect(self, image):
        return self._result


def _identity_matrix():
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _yaw_matrix(degrees):
    theta = math.radians(degrees)
    c, s = math.cos(theta), math.sin(theta)
    return [
        [c, 0.0, s, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [-s, 0.0, c, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _make_landmarker_scorer(blendshapes=None, matrices=None, model_path=None):
    result = FakeLandmarkerResult(
        blendshapes=[blendshapes] if blendshapes is not None else None,
        matrices=matrices,
    )
    return FaceLandmarkerScorer(
        model_path=model_path or Path("fake_model.task"),
        landmarker_factory=lambda: FakeLandmarker(result),
        image_factory=lambda frame: frame,
    )


def test_face_landmarker_olho_fechado_gera_eye_open_score_baixo():
    blendshapes = [FakeCategory("eyeBlinkLeft", 0.9), FakeCategory("eyeBlinkRight", 0.85)]
    scorer = _make_landmarker_scorer(blendshapes=blendshapes, matrices=[_identity_matrix()])

    result = scorer.score(np.zeros((10, 10, 3), dtype=np.uint8))

    assert result.eye_open_score < 0.2


def test_face_landmarker_boca_aberta_sobrancelha_levantada_gera_expression_score_alto():
    blendshapes = [FakeCategory("jawOpen", 0.9), FakeCategory("browInnerUp", 0.8)]
    scorer = _make_landmarker_scorer(blendshapes=blendshapes, matrices=[_identity_matrix()])

    result = scorer.score(np.zeros((10, 10, 3), dtype=np.uint8))

    assert result.expression_score > 0.6


def test_face_landmarker_rosto_frontal_gera_frontality_score_alto():
    scorer = _make_landmarker_scorer(blendshapes=[], matrices=[_identity_matrix()])

    result = scorer.score(np.zeros((10, 10, 3), dtype=np.uint8))

    assert result.frontality_score == pytest.approx(1.0)


def test_face_landmarker_rosto_de_perfil_gera_frontality_score_baixo():
    scorer = _make_landmarker_scorer(blendshapes=[], matrices=[_yaw_matrix(90)])

    result = scorer.score(np.zeros((10, 10, 3), dtype=np.uint8))

    assert result.frontality_score < 0.2


def test_face_landmarker_sem_model_path_faz_fallback_neutro():
    scorer = FaceLandmarkerScorer(model_path=None)

    result = scorer.score(np.zeros((10, 10, 3), dtype=np.uint8))

    assert result == ExpressionScore(eye_open_score=0.5, expression_score=0.5, frontality_score=0.5)


def test_face_landmarker_model_path_inexistente_faz_fallback_neutro(tmp_path):
    scorer = FaceLandmarkerScorer(model_path=tmp_path / "nao_existe.task")

    result = scorer.score(np.zeros((10, 10, 3), dtype=np.uint8))

    assert result == ExpressionScore(eye_open_score=0.5, expression_score=0.5, frontality_score=0.5)


def test_face_quality_scorer_com_landmarker_injetado_combina_scores():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    centered = FaceBox(x=40, y=40, width=20, height=20, confidence=1.0)

    open_eyes_scorer = _make_landmarker_scorer(
        blendshapes=[FakeCategory("eyeBlinkLeft", 0.0), FakeCategory("eyeBlinkRight", 0.0)],
        matrices=[_identity_matrix()],
    )
    closed_eyes_scorer = _make_landmarker_scorer(
        blendshapes=[FakeCategory("eyeBlinkLeft", 0.9), FakeCategory("eyeBlinkRight", 0.9)],
        matrices=[_identity_matrix()],
    )

    score_open = FaceQualityScorer(
        face_detector=FakeFaceDetector([centered]), landmarker_scorer=open_eyes_scorer
    ).score(frame)
    score_closed = FaceQualityScorer(
        face_detector=FakeFaceDetector([centered]), landmarker_scorer=closed_eyes_scorer
    ).score(frame)

    assert score_open > score_closed


def test_face_quality_scorer_sem_landmarker_mantem_comportamento_original():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    centered = FaceBox(x=40, y=40, width=20, height=20, confidence=1.0)

    score = FaceQualityScorer(face_detector=FakeFaceDetector([centered])).score(frame)

    assert score == pytest.approx(1.0)


# --- ThumbnailCandidateRanker --------------------------------------------------


def test_ranker_ordena_por_score_combinado_decrescente():
    candidates = [
        ScoredFrame(frame="a", sharpness_score=10, face_score=0.2),
        ScoredFrame(frame="b", sharpness_score=2, face_score=0.9),
        ScoredFrame(frame="c", sharpness_score=5, face_score=0.5),
    ]
    ranker = ThumbnailCandidateRanker(sharpness_weight=0.5, face_weight=0.5)

    ranked = ranker.rank(candidates)

    assert [c.frame for c in ranked] == ["a", "c", "b"]
    assert ranker.best(candidates).frame == "a"


def test_ranker_pesos_influenciam_o_vencedor():
    candidates = [
        ScoredFrame(frame="sharp", sharpness_score=100, face_score=0.0),
        ScoredFrame(frame="face", sharpness_score=0, face_score=1.0),
    ]

    ranker_sharp = ThumbnailCandidateRanker(sharpness_weight=1.0, face_weight=0.0)
    ranker_face = ThumbnailCandidateRanker(sharpness_weight=0.0, face_weight=1.0)

    assert ranker_sharp.best(candidates).frame == "sharp"
    assert ranker_face.best(candidates).frame == "face"


def test_ranker_best_com_lista_vazia_levanta_erro():
    with pytest.raises(ThumbnailError):
        ThumbnailCandidateRanker().best([])


def test_ranker_com_face_landmarker_prefere_olho_aberto_a_igualdade_do_resto():
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    centered = FaceBox(x=40, y=40, width=20, height=20, confidence=1.0)
    face_detector = FakeFaceDetector([centered])

    open_eyes_scorer = _make_landmarker_scorer(
        blendshapes=[FakeCategory("eyeBlinkLeft", 0.0), FakeCategory("eyeBlinkRight", 0.0)],
        matrices=[_identity_matrix()],
    )
    closed_eyes_scorer = _make_landmarker_scorer(
        blendshapes=[FakeCategory("eyeBlinkLeft", 0.9), FakeCategory("eyeBlinkRight", 0.9)],
        matrices=[_identity_matrix()],
    )

    sharpness = 5.0
    candidates = [
        ScoredFrame(
            frame="olho_fechado",
            sharpness_score=sharpness,
            face_score=FaceQualityScorer(
                face_detector=face_detector, landmarker_scorer=closed_eyes_scorer
            ).score(frame),
        ),
        ScoredFrame(
            frame="olho_aberto",
            sharpness_score=sharpness,
            face_score=FaceQualityScorer(
                face_detector=face_detector, landmarker_scorer=open_eyes_scorer
            ).score(frame),
        ),
    ]

    assert ThumbnailCandidateRanker().best(candidates).frame == "olho_aberto"


# --- ThumbnailBuilder: sem composicao grafica, so o frame escolhido -----------


def test_build_salva_o_melhor_frame_sem_desenhar_nada_por_cima(tmp_path):
    frame_path = tmp_path / "frame.jpg"
    Image.new("RGB", (320, 180), color=(20, 20, 20)).save(frame_path)
    output_path = tmp_path / "thumb.png"

    from clipador.thumbnail.builder import _default_save_frame

    _default_save_frame(frame_path, output_path)

    assert output_path.exists()
    with Image.open(output_path) as saved:
        assert saved.size == (320, 180)
        assert saved.format == "PNG"


# --- ThumbnailBuilder com composer injetado -----------------------------------


class FakeComposer:
    def __init__(self, composed):
        self._composed = composed
        self.calls: list[tuple[Path, str, str]] = []
        self.last_subject = "unset"

    def compose(self, frame_path, headline, aspect_ratio="9:16", subject=None):
        self.calls.append((Path(frame_path), headline, aspect_ratio))
        self.last_subject = subject
        return self._composed


def _builder_with(tmp_path, composer=None):
    from clipador.thumbnail.builder import ThumbnailBuilder

    candidate = tmp_path / "candidate_001.jpg"
    Image.new("RGB", (320, 180), color=(20, 20, 20)).save(candidate)

    return ThumbnailBuilder(
        extractor=types.SimpleNamespace(
            extract=lambda video, out_dir, start=None, end=None: [candidate]
        ),
        sharpness_scorer=types.SimpleNamespace(score=lambda frame: 1.0),
        face_scorer=types.SimpleNamespace(score=lambda frame: 1.0),
        frame_loader=lambda path: types.SimpleNamespace(path=path),
        composer=composer,
    ), candidate


def test_build_com_composer_injetado_salva_o_resultado_da_composicao(tmp_path):
    composed = Image.new("RGB", (320, 180), color=(7, 200, 7))
    composer = FakeComposer(composed)
    builder, candidate = _builder_with(tmp_path, composer)
    output_path = tmp_path / "thumb.png"

    result = builder.build("video.mp4", output_path, tmp_path / "frames", headline="SERA MESMO")

    assert result == output_path
    assert composer.calls == [(candidate, "SERA MESMO", "16:9")]
    with Image.open(output_path) as saved:
        assert saved.convert("RGB").getpixel((0, 0)) == (7, 200, 7)


def test_build_repassa_subject_pro_composer(tmp_path):
    from clipador.thumbnail.face_library import PoliticalFigure

    composed = Image.new("RGB", (320, 180), color=(7, 200, 7))
    composer = FakeComposer(composed)
    builder, candidate = _builder_with(tmp_path, composer)
    subject = PoliticalFigure("lula", "Lula", tmp_path / "lula_fotos")

    builder.build(
        "video.mp4", tmp_path / "thumb.png", tmp_path / "frames", headline="OI", subject=subject
    )

    assert composer.calls == [(candidate, "OI", "16:9")]
    assert composer.last_subject is subject


def test_build_com_composer_que_falha_cai_pro_frame_cru(tmp_path):
    class ExplodingComposer:
        def compose(self, frame_path, headline, aspect_ratio="9:16", subject=None):
            raise RuntimeError("composicao explodiu")

    builder, _ = _builder_with(tmp_path, ExplodingComposer())
    output_path = tmp_path / "thumb.png"

    builder.build("video.mp4", output_path, tmp_path / "frames", headline="OPA")

    with Image.open(output_path) as saved:
        assert saved.convert("RGB").getpixel((0, 0)) == (20, 20, 20)
