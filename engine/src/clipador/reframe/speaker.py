"""Escolha do rosto a seguir no crop (active speaker detection).

Duas implementações de `ActiveSpeakerDetector` convivem aqui:

- `LargestFaceHeuristic`: default histórico, segue o rosto de maior área. Não usa áudio,
  então erra com frequência em entrevista/debate (quem está mais perto da câmera vence,
  mesmo calado).
- `LRASDActiveSpeakerDetector`: integração com o LR-ASD (Light-ASD), que combina os
  lábios do rosto com uma janela de MFCC do áudio para decidir quem realmente fala.
  O modelo é vendorizado (não existe pacote pip); enquanto ele não estiver presente o
  detector cai de volta na heurística de forma transparente, só registrando um aviso.

Como vendorizar o LR-ASD (passo manual, ainda pendente)
-------------------------------------------------------
1. `git clone https://github.com/Junhua-Liao/LR-ASD vendor/lr_asd` (licença MIT,
   PyTorch puro, 0.84M parâmetros, sem ops CUDA customizadas).
2. Baixar os pesos do repositório e deixá-los em `vendor/lr_asd/weight/`. O peso usado
   por padrão aqui é `finetuning_TalkSet.model` (o `pretrain_AVA_CVPR.model` também
   serve, basta passar `weight_name`).
3. Patch de portabilidade: o `ASD.py` original chama `.cuda()` direto no construtor
   (assume GPU sempre presente) e faz `torch.load(path)` sem `map_location` (quebra
   sem GPU). Removidos os `.cuda()` fixos e adicionado `map_location="cpu"` no load
   dos pesos — o `LRASDActiveSpeakerDetector` decide o device em runtime
   (`device=` explícito, ou auto-detecta `cuda` via `torch.cuda.is_available()`) e
   move o modelo com `.to(device)` depois de carregado, então funciona nas duas
   situações sem exigir GPU.
4. Instalar os extras de vídeo (`pip install -e ".[video]"`, que já traz `librosa`) e
   apontar o detector para a pasta:
   `LRASDActiveSpeakerDetector(model_dir=Path("vendor/lr_asd"))`.

Enquanto os passos acima não forem feitos, `LRASDActiveSpeakerDetector.available` é
False e o pipeline continua funcionando com a heurística.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from clipador.reframe.models import FaceBox

logger = logging.getLogger(__name__)

DEFAULT_WEIGHT_NAME = "finetuning_TalkSet.model"
# LR-ASD foi treinado com vídeo a 25 fps e MFCC a 100 fps: 4 quadros de áudio por quadro de vídeo.
AUDIO_FRAMES_PER_VIDEO_FRAME = 4
MFCC_SAMPLE_RATE = 16_000
MFCC_HOP_LENGTH = 160  # 10 ms em 16 kHz
MFCC_WIN_LENGTH = 400  # 25 ms em 16 kHz


class ActiveSpeakerDetector(ABC):
    @abstractmethod
    def select_active_face(
        self, faces: Sequence[FaceBox], audio_context: Any = None
    ) -> FaceBox | None:
        """Devolve o rosto que o crop deve seguir, ou None quando nao ha candidato confiavel."""


class LargestFaceHeuristic(ActiveSpeakerDetector):
    """Segue o rosto de maior area (proxy de "quem esta em primeiro plano")."""

    def __init__(self, min_confidence: float = 0.0) -> None:
        self.min_confidence = min_confidence

    def select_active_face(
        self, faces: Sequence[FaceBox], audio_context: Any = None
    ) -> FaceBox | None:
        candidates = [face for face in faces if face.confidence >= self.min_confidence]
        if not candidates:
            return None
        return max(candidates, key=lambda face: (face.area, face.confidence))


@dataclass(frozen=True)
class SpeakerContext:
    """Sinais de áudio e vídeo ao redor do instante amostrado.

    É o que a heurística ignora e o LR-ASD precisa: `frames` são os quadros consecutivos
    do trecho (mesmo cena, ordem temporal) e `audio_path`/`start`/`end` delimitam a
    janela de áudio correspondente. Quanto mais quadros, melhor o modelo enxerga o
    movimento dos lábios; com um único quadro o forward tende a falhar nas convoluções
    temporais e o detector cai na heurística.
    """

    audio_path: Path | None = None
    start: float = 0.0
    end: float = 0.0
    frames: tuple[Any, ...] = field(default_factory=tuple)

    @classmethod
    def from_frame(
        cls, frame: Any, audio_path: Path | None, start: float, end: float
    ) -> SpeakerContext:
        return cls(audio_path=audio_path, start=start, end=end, frames=(frame,))

    @property
    def is_usable(self) -> bool:
        return bool(self.frames) and self.audio_path is not None and self.end > self.start


def extract_mfcc_window(
    audio_path: str | Path,
    start: float,
    end: float,
    n_mfcc: int = 13,
    sample_rate: int = MFCC_SAMPLE_RATE,
) -> Any:
    """Extrai os MFCC da janela [start, end) do áudio no formato (quadros, n_mfcc).

    Usa hop de 10 ms e janela de 25 ms, a mesma configuração com que o LR-ASD foi
    treinado. `librosa` é importado aqui dentro porque é um extra de vídeo.
    """
    import librosa

    duration = end - start
    if duration <= 0:
        raise ValueError(f"Janela de áudio inválida: start={start}, end={end}")

    waveform, sr = librosa.load(
        str(audio_path), sr=sample_rate, offset=max(0.0, start), duration=duration
    )
    mfcc = librosa.feature.mfcc(
        y=waveform,
        sr=sr,
        n_mfcc=n_mfcc,
        hop_length=MFCC_HOP_LENGTH,
        win_length=MFCC_WIN_LENGTH,
    )
    return mfcc.T


def crop_face_patch(frame: Any, face: FaceBox, size: int = 112, padding: float = 0.4) -> Any:
    """Recorta um quadrado em torno do rosto e devolve um patch cinza `size`x`size`.

    Redimensiona por vizinho mais próximo com numpy para não depender do OpenCV neste
    módulo. O LR-ASD espera exatamente 112x112 em escala de cinza.
    """
    import numpy as np

    frame_height, frame_width = frame.shape[:2]
    center_x, center_y = face.center
    half = max(face.width, face.height) * (1.0 + padding) / 2

    left = max(0, min(int(round(center_x - half)), frame_width - 1))
    top = max(0, min(int(round(center_y - half)), frame_height - 1))
    right = max(left + 1, min(int(round(center_x + half)), frame_width))
    bottom = max(top + 1, min(int(round(center_y + half)), frame_height))

    patch = np.asarray(frame[top:bottom, left:right], dtype="float32")
    if patch.ndim == 3:
        patch = patch.mean(axis=2)

    rows = np.linspace(0, patch.shape[0] - 1, size).round().astype(int)
    cols = np.linspace(0, patch.shape[1] - 1, size).round().astype(int)
    return patch[rows][:, cols]


def _mean_score(score: Any) -> float:
    """Achata a saída do `lossAV` (tensor, array ou lista aninhada) numa média escalar."""
    values = score.tolist() if hasattr(score, "tolist") else score
    flat: list[float] = []
    stack = [values]
    while stack:
        item = stack.pop()
        if isinstance(item, (list, tuple)):
            stack.extend(item)
        else:
            flat.append(float(item))
    if not flat:
        raise ValueError("Score vazio devolvido pelo LR-ASD")
    return sum(flat) / len(flat)


class LRASDActiveSpeakerDetector(ActiveSpeakerDetector):
    """Active speaker detection com LR-ASD, com fallback automático para a heurística.

    O forward reproduz o `Columbia_test.py` do repositório oficial:

        embed_a = model.model.forward_audio_frontend(input_a)   # (1, 4*T, n_mfcc)
        embed_v = model.model.forward_visual_frontend(input_v)   # (1, T, 112, 112)
        out = model.model.forward_audio_visual_backend(embed_a, embed_v)
        score = model.lossAV.forward(out, labels=None)

    Um score por rosto candidato; vence o maior. Os quadros vêm de `SpeakerContext` e a
    mesma caixa de rosto é aplicada a todos eles (aproximação de face track: o
    reenquadramento amostra intervalos curtos, onde o rosto quase não se move).
    """

    def __init__(
        self,
        model_dir: Path | None = None,
        weight_name: str = DEFAULT_WEIGHT_NAME,
        min_confidence: float = 0.0,
        n_mfcc: int = 13,
        fallback: ActiveSpeakerDetector | None = None,
        model_factory: Callable[[], Any] | None = None,
        device: str | None = None,
    ) -> None:
        self.model_dir = Path(model_dir) if model_dir is not None else None
        self.weight_name = weight_name
        self.min_confidence = min_confidence
        self.n_mfcc = n_mfcc
        self.fallback = fallback or LargestFaceHeuristic(min_confidence)
        self._model_factory = model_factory
        # None = detecta cuda automaticamente ao carregar o modelo real; com
        # `model_factory` (usado nos testes) o modelo fica em "cpu" e nunca e movido,
        # entao as fakes nao precisam implementar `.to()`.
        self.device = device
        self._resolved_device = "cpu"
        self._model: Any | None = None
        self._disabled = False

        if model_factory is None and not self.available:
            logger.warning(
                "LR-ASD indisponível em %s; usando %s. Vendorize o modelo para ativar "
                "a deteccao real de quem fala (ver docstring de speaker.py).",
                self.model_dir or "<model_dir não informado>",
                type(self.fallback).__name__,
            )

    @property
    def weight_path(self) -> Path | None:
        return None if self.model_dir is None else self.model_dir / "weight" / self.weight_name

    @property
    def available(self) -> bool:
        """True quando o código e os pesos vendorizados estão no disco."""
        if self._model_factory is not None:
            return True
        if self.model_dir is None:
            return False
        weight_path = self.weight_path
        return (self.model_dir / "ASD.py").is_file() and weight_path is not None and weight_path.is_file()

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self._model_factory is not None:
            self._model = self._model_factory()
            return self._model

        import sys

        import torch

        model_dir = str(self.model_dir)
        if model_dir not in sys.path:
            sys.path.insert(0, model_dir)
        from ASD import ASD  # type: ignore[import-not-found]

        model = ASD()
        model.loadParameters(str(self.weight_path))
        model.eval()

        # Modelo puro PyTorch (0.84M params, sem kernel CUDA custom): move pra GPU
        # quando disponivel em vez de forcar CPU. `loadParameters` sempre le os pesos
        # em CPU (map_location="cpu") e `copy_` cuida da transferencia de device.
        self._resolved_device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        if self._resolved_device != "cpu":
            model = model.to(self._resolved_device)

        self._model = model
        return model

    def _score_face(self, model: Any, torch: Any, audio_feature: Any, frames: Sequence[Any], face: FaceBox) -> float:
        import numpy as np

        video_feature = np.stack([crop_face_patch(frame, face) for frame in frames])
        length = min(len(video_feature), len(audio_feature) // AUDIO_FRAMES_PER_VIDEO_FRAME)
        if length < 1:
            raise ValueError(
                f"Janela curta demais: {len(frames)} quadros de vídeo para "
                f"{len(audio_feature)} de áudio"
            )

        input_a = torch.FloatTensor(audio_feature[: length * AUDIO_FRAMES_PER_VIDEO_FRAME]).unsqueeze(0)
        input_v = torch.FloatTensor(video_feature[:length]).unsqueeze(0)
        if self._resolved_device != "cpu":
            input_a = input_a.to(self._resolved_device)
            input_v = input_v.to(self._resolved_device)

        with torch.no_grad():
            embed_a = model.model.forward_audio_frontend(input_a)
            embed_v = model.model.forward_visual_frontend(input_v)
            out = model.model.forward_audio_visual_backend(embed_a, embed_v)
            score = model.lossAV.forward(out, labels=None)
        return _mean_score(score)

    def select_active_face(
        self, faces: Sequence[FaceBox], audio_context: Any = None
    ) -> FaceBox | None:
        candidates = [face for face in faces if face.confidence >= self.min_confidence]
        if not candidates:
            return None
        # Com um só rosto o modelo não muda a decisão e custa um forward inteiro.
        if len(candidates) == 1:
            return candidates[0]

        if self._disabled or not self.available:
            return self.fallback.select_active_face(faces, audio_context)
        if not isinstance(audio_context, SpeakerContext) or not audio_context.is_usable:
            logger.debug("Sem SpeakerContext utilizável; caindo na heurística de maior rosto")
            return self.fallback.select_active_face(faces, audio_context)

        try:
            import torch

            model = self._load_model()
            audio_feature = extract_mfcc_window(
                audio_context.audio_path,
                audio_context.start,
                audio_context.end,
                n_mfcc=self.n_mfcc,
            )
            scores = [
                self._score_face(model, torch, audio_feature, audio_context.frames, face)
                for face in candidates
            ]
        except Exception:
            # Modelo quebrado ou dependência faltando não pode derrubar o pipeline inteiro.
            self._disabled = True
            logger.warning(
                "Falha ao rodar o LR-ASD; desativando e usando %s daqui em diante",
                type(self.fallback).__name__,
                exc_info=True,
            )
            return self.fallback.select_active_face(faces, audio_context)

        return max(zip(candidates, scores), key=lambda pair: pair[1])[0]
