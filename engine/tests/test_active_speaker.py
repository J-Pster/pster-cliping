"""LR-ASD: fallback sem modelo vendorizado + integracao com torch/librosa stubados.

Nenhum teste aqui exige PyTorch, librosa ou os pesos reais do LR-ASD instalados.
"""

import contextlib
import sys
import types

import numpy as np
import pytest

from clipador.reframe import (
    FaceBox,
    LargestFaceHeuristic,
    LRASDActiveSpeakerDetector,
    SpeakerContext,
    crop_face_patch,
    extract_mfcc_window,
)

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


def _frame_with_bright_face(face, brightness=200.0):
    """Frame preto com um retangulo claro em cima de `face`, para o fake model pontuar."""
    frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype="float32")
    top = int(face.y)
    left = int(face.x)
    frame[top : top + int(face.height), left : left + int(face.width)] = brightness
    return frame


# --- stubs -----------------------------------------------------------------


class _FakeTensor:
    def __init__(self, data):
        self.data = np.asarray(data)
        self.device = "cpu"

    def unsqueeze(self, dim):
        return self

    def to(self, device):
        self.device = device
        return self


@pytest.fixture
def torch_stub(monkeypatch):
    module = types.ModuleType("torch")
    module.FloatTensor = _FakeTensor
    module.no_grad = contextlib.nullcontext
    monkeypatch.setitem(sys.modules, "torch", module)
    return module


@pytest.fixture
def librosa_stub(monkeypatch):
    calls = {}
    module = types.ModuleType("librosa")
    feature = types.ModuleType("librosa.feature")

    def load(path, sr=None, offset=0.0, duration=None):
        calls["load"] = {"path": path, "sr": sr, "offset": offset, "duration": duration}
        return np.zeros(int(sr * duration), dtype="float32"), sr

    def mfcc(y, sr, n_mfcc, hop_length, win_length):
        calls["mfcc"] = {
            "sr": sr,
            "n_mfcc": n_mfcc,
            "hop_length": hop_length,
            "win_length": win_length,
        }
        return np.zeros((n_mfcc, 40), dtype="float32")

    module.load = load
    feature.mfcc = mfcc
    module.feature = feature
    monkeypatch.setitem(sys.modules, "librosa", module)
    monkeypatch.setitem(sys.modules, "librosa.feature", feature)
    return calls


class _FakeInner:
    """Repassa os tensores adiante; o score sai do brilho do patch de rosto."""

    def forward_audio_frontend(self, x):
        return x

    def forward_visual_frontend(self, x):
        return x

    def forward_audio_visual_backend(self, embed_a, embed_v):
        return embed_v


class _FakeLoss:
    def forward(self, out, labels=None):
        return [float(out.data.mean())]


class FakeASD:
    def __init__(self):
        self.model = _FakeInner()
        self.lossAV = _FakeLoss()


def _vendored_model_dir(tmp_path):
    model_dir = tmp_path / "lr_asd"
    (model_dir / "weight").mkdir(parents=True)
    (model_dir / "ASD.py").write_text("# stub", encoding="utf-8")
    (model_dir / "weight" / "finetuning_TalkSet.model").write_bytes(b"stub")
    return model_dir


# --- fallback sem modelo vendorizado ---------------------------------------


def test_sem_model_dir_cai_na_heuristica_de_maior_rosto():
    detector = LRASDActiveSpeakerDetector()
    pequeno = _face(300.0, width=80.0, height=80.0)
    grande = _face(1500.0, width=260.0, height=260.0)

    assert detector.available is False
    assert detector.select_active_face([pequeno, grande]) is grande


def test_model_dir_sem_arquivos_vendorizados_nao_quebra(tmp_path):
    detector = LRASDActiveSpeakerDetector(model_dir=tmp_path / "lr_asd")
    esquerda = _face(300.0, width=300.0, height=300.0)
    direita = _face(1500.0, width=100.0, height=100.0)

    assert detector.available is False
    assert detector.select_active_face([esquerda, direita]) is esquerda


def test_peso_ausente_mantem_detector_indisponivel(tmp_path):
    model_dir = tmp_path / "lr_asd"
    (model_dir / "weight").mkdir(parents=True)
    (model_dir / "ASD.py").write_text("# stub", encoding="utf-8")

    assert LRASDActiveSpeakerDetector(model_dir=model_dir).available is False


def test_codigo_e_peso_presentes_marcam_o_detector_disponivel(tmp_path):
    detector = LRASDActiveSpeakerDetector(model_dir=_vendored_model_dir(tmp_path))

    assert detector.available is True
    assert detector.weight_path.name == "finetuning_TalkSet.model"


def test_sem_rosto_ou_abaixo_da_confianca_devolve_none():
    detector = LRASDActiveSpeakerDetector(min_confidence=0.5)

    assert detector.select_active_face([]) is None
    assert detector.select_active_face([_face(300.0, confidence=0.1)]) is None


def test_modelo_disponivel_mas_sem_contexto_de_audio_usa_fallback():
    def _explode():
        raise AssertionError("modelo nao deveria ser carregado sem contexto de audio")

    detector = LRASDActiveSpeakerDetector(model_factory=_explode)
    pequeno = _face(300.0, width=80.0, height=80.0)
    grande = _face(1500.0, width=260.0, height=260.0)

    assert detector.select_active_face([pequeno, grande], audio_context=None) is grande


def test_um_unico_rosto_nao_carrega_o_modelo(tmp_path):
    def _explode():
        raise AssertionError("modelo nao deveria ser carregado com um unico rosto")

    detector = LRASDActiveSpeakerDetector(model_factory=_explode)
    unico = _face(300.0)
    contexto = SpeakerContext.from_frame(
        _frame_with_bright_face(unico), tmp_path / "audio.wav", 0.0, 1.0
    )

    assert detector.select_active_face([unico], contexto) is unico


# --- MFCC ------------------------------------------------------------------


def test_extract_mfcc_window_devolve_quadros_por_coeficiente(librosa_stub, tmp_path):
    mfcc = extract_mfcc_window(tmp_path / "audio.wav", 2.0, 3.0, n_mfcc=13)

    assert mfcc.shape == (40, 13)
    assert librosa_stub["load"]["offset"] == 2.0
    assert librosa_stub["load"]["duration"] == 1.0
    assert librosa_stub["load"]["sr"] == 16_000
    # 10 ms de hop e 25 ms de janela em 16 kHz: o setup com que o LR-ASD foi treinado.
    assert librosa_stub["mfcc"]["hop_length"] == 160
    assert librosa_stub["mfcc"]["win_length"] == 400
    assert librosa_stub["mfcc"]["n_mfcc"] == 13


def test_extract_mfcc_window_rejeita_janela_vazia(librosa_stub, tmp_path):
    with pytest.raises(ValueError):
        extract_mfcc_window(tmp_path / "audio.wav", 3.0, 3.0)


# --- crop de rosto ---------------------------------------------------------


def test_crop_face_patch_devolve_patch_cinza_112():
    face = _face(960.0, width=200.0, height=200.0)
    patch = crop_face_patch(_frame_with_bright_face(face), face)

    assert patch.shape == (112, 112)
    assert patch.max() > 0


def test_crop_face_patch_respeita_as_bordas_do_frame():
    face = _face(20.0, width=200.0, height=200.0, center_y=20.0)
    patch = crop_face_patch(_frame_with_bright_face(face), face)

    assert patch.shape == (112, 112)
    assert np.isfinite(patch).all()


# --- integracao completa com torch + modelo stubados -----------------------


def _cenario_dois_rostos(tmp_path, model_factory=FakeASD):
    calado = _face(400.0, width=260.0, height=260.0)
    falante = _face(1500.0, width=200.0, height=200.0)
    frame = _frame_with_bright_face(falante)
    contexto = SpeakerContext(
        audio_path=tmp_path / "audio.wav", start=1.0, end=2.0, frames=(frame, frame, frame)
    )
    detector = LRASDActiveSpeakerDetector(model_factory=model_factory)
    return detector, [calado, falante], contexto, falante


def test_lr_asd_escolhe_o_rosto_com_maior_score_mesmo_sendo_menor(
    torch_stub, librosa_stub, tmp_path
):
    detector, faces, contexto, falante = _cenario_dois_rostos(tmp_path)

    escolhido = detector.select_active_face(faces, contexto)

    assert escolhido is falante
    # A heuristica antiga escolheria o rosto maior, provando que o modelo mudou a decisao.
    assert LargestFaceHeuristic().select_active_face(faces) is not falante


def test_modelo_carregado_uma_unica_vez(torch_stub, librosa_stub, tmp_path):
    carregamentos = []

    def factory():
        carregamentos.append(1)
        return FakeASD()

    detector, faces, contexto, _ = _cenario_dois_rostos(tmp_path, model_factory=factory)
    detector.select_active_face(faces, contexto)
    detector.select_active_face(faces, contexto)

    assert len(carregamentos) == 1


def test_falha_no_forward_desativa_o_modelo_e_cai_na_heuristica(
    torch_stub, librosa_stub, tmp_path
):
    class ModeloQuebrado(FakeASD):
        def __init__(self):
            super().__init__()
            self.model.forward_audio_frontend = self._boom

        @staticmethod
        def _boom(_):
            raise RuntimeError("peso incompativel")

    detector, faces, contexto, falante = _cenario_dois_rostos(
        tmp_path, model_factory=ModeloQuebrado
    )

    escolhido = detector.select_active_face(faces, contexto)

    assert escolhido is LargestFaceHeuristic().select_active_face(faces)
    assert escolhido is not falante
    assert detector._disabled is True


def test_janela_de_audio_curta_demais_cai_na_heuristica(torch_stub, monkeypatch, tmp_path):
    module = types.ModuleType("librosa")
    feature = types.ModuleType("librosa.feature")
    module.load = lambda path, sr=None, offset=0.0, duration=None: (
        np.zeros(16, dtype="float32"),
        sr,
    )
    # Menos de 4 quadros de MFCC: nao da nem um quadro de video alinhado.
    feature.mfcc = lambda y, sr, n_mfcc, hop_length, win_length: np.zeros(
        (n_mfcc, 2), dtype="float32"
    )
    module.feature = feature
    monkeypatch.setitem(sys.modules, "librosa", module)
    monkeypatch.setitem(sys.modules, "librosa.feature", feature)

    detector, faces, contexto, falante = _cenario_dois_rostos(tmp_path)

    escolhido = detector.select_active_face(faces, contexto)

    assert escolhido is LargestFaceHeuristic().select_active_face(faces)
    assert escolhido is not falante


# --- device (GPU vs CPU) ----------------------------------------------------


def _write_fake_asd_module(model_dir):
    (model_dir / "weight").mkdir(parents=True)
    (model_dir / "weight" / "finetuning_TalkSet.model").write_bytes(b"stub")
    (model_dir / "ASD.py").write_text(
        "class _Inner:\n"
        "    def forward_audio_frontend(self, x):\n"
        "        return x\n"
        "    def forward_visual_frontend(self, x):\n"
        "        return x\n"
        "    def forward_audio_visual_backend(self, a, v):\n"
        "        return v\n"
        "\n"
        "class _Loss:\n"
        "    def forward(self, out, labels=None):\n"
        "        return [float(out.data.mean())]\n"
        "\n"
        "class ASD:\n"
        "    def __init__(self):\n"
        "        self.model = _Inner()\n"
        "        self.lossAV = _Loss()\n"
        "        self.device = 'cpu'\n"
        "    def loadParameters(self, path):\n"
        "        pass\n"
        "    def eval(self):\n"
        "        return self\n"
        "    def to(self, device):\n"
        "        self.device = device\n"
        "        return self\n",
        encoding="utf-8",
    )


def test_modelo_real_vai_pra_cuda_quando_disponivel(monkeypatch, librosa_stub, tmp_path):
    model_dir = tmp_path / "lr_asd"
    _write_fake_asd_module(model_dir)

    torch_module = types.ModuleType("torch")
    torch_module.FloatTensor = _FakeTensor
    torch_module.no_grad = contextlib.nullcontext
    torch_module.cuda = types.SimpleNamespace(is_available=lambda: True)
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.delitem(sys.modules, "ASD", raising=False)

    falante = _face(1500.0, width=200.0, height=200.0)
    contexto = SpeakerContext(
        audio_path=tmp_path / "audio.wav",
        start=1.0,
        end=2.0,
        frames=(_frame_with_bright_face(falante),) * 3,
    )
    detector = LRASDActiveSpeakerDetector(model_dir=model_dir)

    detector.select_active_face([falante, _face(400.0, width=260.0, height=260.0)], contexto)

    assert detector._resolved_device == "cuda"
    assert detector._model.device == "cuda"
    sys.modules.pop("ASD", None)


def test_modelo_real_fica_em_cpu_sem_cuda_disponivel(monkeypatch, librosa_stub, tmp_path):
    model_dir = tmp_path / "lr_asd"
    _write_fake_asd_module(model_dir)

    torch_module = types.ModuleType("torch")
    torch_module.FloatTensor = _FakeTensor
    torch_module.no_grad = contextlib.nullcontext
    torch_module.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", torch_module)
    monkeypatch.delitem(sys.modules, "ASD", raising=False)

    falante = _face(1500.0, width=200.0, height=200.0)
    contexto = SpeakerContext(
        audio_path=tmp_path / "audio.wav",
        start=1.0,
        end=2.0,
        frames=(_frame_with_bright_face(falante),) * 3,
    )
    detector = LRASDActiveSpeakerDetector(model_dir=model_dir)

    detector.select_active_face([falante, _face(400.0, width=260.0, height=260.0)], contexto)

    assert detector._resolved_device == "cpu"
    assert detector._model.device == "cpu"
    sys.modules.pop("ASD", None)


def test_fallback_customizado_e_respeitado(tmp_path):
    class SempreOPrimeiro(LargestFaceHeuristic):
        def select_active_face(self, faces, audio_context=None):
            return faces[0] if faces else None

    detector = LRASDActiveSpeakerDetector(fallback=SempreOPrimeiro())
    pequeno = _face(300.0, width=80.0, height=80.0)
    grande = _face(1500.0, width=260.0, height=260.0)

    assert detector.select_active_face([pequeno, grande]) is pequeno
