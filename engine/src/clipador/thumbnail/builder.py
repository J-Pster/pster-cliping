"""Liga as pecas da etapa [8]: extrai candidatos, pontua e ranqueia a thumbnail final.

Sem `composer` injetado a thumbnail e o proprio frame escolhido, sem nada desenhado por
cima; com ele, o frame passa pela composicao (fundo tratado, recorte da pessoa, headline
e destaque) antes de ser salvo.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from clipador.thumbnail.composer import ThumbnailComposer
from clipador.thumbnail.extractor import IFrameExtractor
from clipador.thumbnail.face_library import PoliticalFigure
from clipador.thumbnail.face_quality import FaceQualityScorer
from clipador.thumbnail.models import ScoredFrame, ThumbnailError
from clipador.thumbnail.ranker import ThumbnailCandidateRanker
from clipador.thumbnail.sharpness import SharpnessScorer

logger = logging.getLogger(__name__)


def _default_frame_loader(path: Path) -> Any:
    # cv2.imread(str(path)) usa fopen com a codepage ANSI do Windows por baixo dos panos:
    # falha silenciosa (retorna None) pra qualquer caminho com acento (á, é, ô...), comum
    # em nomes de arquivo/pasta em portugues. Le os bytes via pathlib (sempre correto com
    # Unicode) e decodifica em memoria, contornando o fopen do OpenCV.
    import cv2
    import numpy as np

    data = np.frombuffer(Path(path).read_bytes(), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _default_save_frame(frame_path: Path, output_path: Path) -> None:
    Image.open(frame_path).convert("RGB").save(output_path)


def _aspect_ratio_of(frame_path: Path) -> str:
    with Image.open(frame_path) as image:
        width, height = image.size
    return "9:16" if height > width else "16:9"


class ThumbnailBuilder:
    """Do video ao arquivo de thumbnail: I-frames -> nitidez + rosto -> ranking -> salva o melhor.

    `ScoredFrame.frame` carrega aqui o *caminho* do candidato, nao a matriz do frame:
    a matriz e usada so para pontuar e o ranker olha apenas os scores.
    """

    def __init__(
        self,
        extractor: IFrameExtractor | None = None,
        sharpness_scorer: SharpnessScorer | None = None,
        face_scorer: FaceQualityScorer | None = None,
        ranker: ThumbnailCandidateRanker | None = None,
        frame_loader: Callable[[Path], Any] | None = None,
        save_frame: Callable[[Path, Path], None] | None = None,
        composer: ThumbnailComposer | None = None,
    ) -> None:
        self.composer = composer
        self.extractor = extractor or IFrameExtractor()
        self.sharpness_scorer = sharpness_scorer or SharpnessScorer()
        self.face_scorer = face_scorer or FaceQualityScorer()
        self.ranker = ranker or ThumbnailCandidateRanker()
        self.frame_loader = frame_loader or _default_frame_loader
        self.save_frame = save_frame or _default_save_frame

    def build(
        self,
        video_path: str | Path,
        output_path: str | Path,
        candidates_dir: str | Path,
        start: float | None = None,
        end: float | None = None,
        headline: str = "",
        subject: PoliticalFigure | None = None,
    ) -> Path:
        paths = self.extractor.extract(video_path, candidates_dir, start, end)
        if not paths:
            raise ThumbnailError(f"Nenhum frame candidato extraido de {video_path}")

        scored: list[ScoredFrame] = []
        for path in paths:
            frame = self.frame_loader(path)
            if frame is None:
                continue
            scored.append(
                ScoredFrame(
                    frame=path,
                    sharpness_score=self.sharpness_scorer.score(frame),
                    face_score=self.face_scorer.score(frame),
                )
            )

        if not scored:
            raise ThumbnailError(f"Nenhum frame candidato legivel em {candidates_dir}")

        best = self.ranker.best(scored)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        best_frame = Path(best.frame)

        if self.composer is not None:
            try:
                aspect_ratio = _aspect_ratio_of(best_frame)
                self.composer.compose(best_frame, headline, aspect_ratio, subject).save(output_path)
                return output_path
            except Exception as exc:
                logger.warning(
                    "Composicao da thumbnail falhou (%s); salvando o frame escolhido cru.", exc
                )

        self.save_frame(best_frame, output_path)
        return output_path
