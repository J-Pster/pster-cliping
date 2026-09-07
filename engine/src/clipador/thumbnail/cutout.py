"""Recorte da pessoa do fundo do frame via rembg (dependencia opcional, import lazy).

Sem rembg instalado (ou com falha na remocao), `cut()` devolve None em vez de levantar:
a composicao da thumbnail continua so com o frame tratado, nunca derruba o clipe.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Callable

from PIL import Image

logger = logging.getLogger(__name__)


class PersonCutout:
    """Recorta a pessoa e devolve RGBA com fundo transparente.

    `remove_fn` recebe os bytes da imagem e devolve os bytes de um PNG RGBA; quando nao
    injetado, e resolvido uma unica vez a partir do `rembg`.
    """

    def __init__(self, remove_fn: Callable[[bytes], bytes] | None = None) -> None:
        self._remove_fn = remove_fn
        self._probed = remove_fn is not None

    def _probe(self) -> None:
        if self._probed:
            return
        self._probed = True
        try:
            from rembg import remove
        except Exception as exc:
            logger.warning(
                "rembg indisponivel (%s); a thumbnail segue sem recorte da pessoa. "
                "Instale com: pip install 'clipador[thumbnail-ai]'",
                exc,
            )
            return
        self._remove_fn = remove

    @property
    def available(self) -> bool:
        self._probe()
        return self._remove_fn is not None

    def cut(self, frame_path: str | Path) -> Image.Image | None:
        if not self.available:
            return None

        remove_fn = self._remove_fn
        try:
            output = remove_fn(Path(frame_path).read_bytes())
            return Image.open(io.BytesIO(output)).convert("RGBA")
        except Exception as exc:
            logger.warning("Falha ao recortar a pessoa de %s: %s", frame_path, exc)
            return None
