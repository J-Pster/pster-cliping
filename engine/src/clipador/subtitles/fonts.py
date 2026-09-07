"""Fontes embarcadas da legenda: resolucao do arquivo .ttf e medicao de texto.

Por que embarcar a fonte em vez de confiar no que a maquina tem instalado: o burn-in
roda no libass (filtro `ass` do ffmpeg), que resolve o campo `Fontname` do estilo pelo
fontconfig do sistema. Quando a fonte pedida nao existe ali, o libass NAO falha - ele
cai numa fonte generica em silencio e o clipe sai com a legenda errada, sem nada no log.
Apontar `fontsdir` pra `assets/fonts` faz o mesmo .ttf versionado no repo valer em
qualquer maquina, no CI e no container.

`BUNDLED_FONTS` mapeia o nome que vai no campo `Fontname` do ASS para o arquivo. Esse
nome NAO e o nome do arquivo: o libass casa pela tabela `name` do TTF (familia ou
fullname). Montserrat e o unico caso aqui em que familia ("Montserrat") e peso
("ExtraBold") sao campos separados, entao o valor usado e o fullname completo; as outras
tres sao familias de peso unico, cujo nome de familia ja e o nome final.

A medicao existe pro modo de animacao `pop`, que posiciona cada palavra com `\\pos`
explicito e por isso precisa saber a largura de cada uma ANTES do render. Medimos com o
FreeType do Pillow (dependencia obrigatoria do projeto) no MESMO .ttf que o libass vai
usar. Como o builder posiciona toda palavra explicitamente, o libass nunca refaz layout
proprio: o que importa e a consistencia interna da medicao, nao bater 1:1 com o shaper
do libass.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

# Diretorio padrao, relativo ao cwd - mesma convencao do `models/blaze_face_short_range.tflite`
# usado pelo detector de rosto (a CLI expoe o caminho como parametro).
DEFAULT_FONTS_DIR = Path("assets/fonts")

BUNDLED_FONTS: dict[str, str] = {
    "Montserrat ExtraBold": "Montserrat-ExtraBold.ttf",
    "Anton": "Anton-Regular.ttf",
    "Archivo Black": "ArchivoBlack-Regular.ttf",
    "Bebas Neue": "BebasNeue-Regular.ttf",
}

# Tamanho de referencia da medicao. Medimos sempre neste em-size e escalamos linearmente
# para o `font_size` real: o avanco horizontal de um glifo e linear no em-size, e um
# valor grande diminui o erro de arredondamento do rasterizador para <0.1%.
_REFERENCE_EM = 1000


class FontNotFoundError(RuntimeError):
    """A fonte pedida nao esta em `fonts_dir`. Erro duro de proposito: o libass cairia
    numa fonte generica em silencio, e o clipe sairia errado sem ninguem perceber."""


def font_file_for(font_name: str, fonts_dir: Path | str = DEFAULT_FONTS_DIR) -> Path:
    """Caminho do .ttf embarcado que corresponde ao `Fontname` do estilo ASS."""
    file_name = BUNDLED_FONTS.get(font_name)
    if file_name is None:
        raise FontNotFoundError(
            f"Fonte {font_name!r} nao esta embarcada. Disponiveis: {sorted(BUNDLED_FONTS)}"
        )
    path = Path(fonts_dir) / file_name
    if not path.is_file():
        raise FontNotFoundError(
            f"Arquivo da fonte {font_name!r} nao encontrado em {path}. "
            "Rode `python scripts/fetch_fonts.py` a partir de engine/."
        )
    return path


@lru_cache(maxsize=8)
def _reference_font(path_str: str) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path_str, _REFERENCE_EM)


def _sfnt_tables(data: bytes) -> dict[str, int]:
    """Offset de cada tabela do arquivo TrueType. Parser minimo, so o diretorio."""
    (table_count,) = struct.unpack(">H", data[4:6])
    tables: dict[str, int] = {}
    for index in range(table_count):
        entry = 12 + 16 * index
        tag, _checksum, offset, _length = struct.unpack(">4sIII", data[entry : entry + 16])
        tables[tag.decode("latin-1")] = offset
    return tables


@lru_cache(maxsize=8)
def em_scale(path_str: str) -> float:
    """Quanto de EM a fonte recebe por unidade de `Fontsize` do estilo ASS.

    O campo `Fontsize` do ASS NAO e o em da fonte. Por compatibilidade com o VSFilter, o
    libass pede o tamanho ao FreeType com `FT_SIZE_REQUEST_TYPE_REAL_DIM` e a altura
    corrigida por `(hhea.ascender - hhea.descender) / (OS/2.usWinAscent + usWinDescent)`.
    Fazendo a conta, o em efetivo resultante e:

        em = Fontsize * unitsPerEm / (usWinAscent + usWinDescent)

    Para as fontes embarcadas isso da entre 0.58 (Anton) e 0.77 (Bebas Neue): medir com o
    em cru do Pillow superestimaria a largura do texto em ate 42%, o que erra a quebra de
    linha e desloca todo `\\pos` do modo "pop". Conferido contra o render real do libass
    nas quatro fontes, com erro abaixo de 0.5%.
    """
    data = Path(path_str).read_bytes()
    tables = _sfnt_tables(data)
    head, os2 = tables.get("head"), tables.get("OS/2")
    if head is None or os2 is None:
        # Fonte sem as tabelas usadas pela heuristica do VSFilter: o libass cai no
        # dimensionamento por em cru, entao aqui tambem.
        return 1.0
    (units_per_em,) = struct.unpack(">H", data[head + 18 : head + 20])
    win_ascent, win_descent = struct.unpack(">HH", data[os2 + 74 : os2 + 78])
    total = win_ascent + win_descent
    return units_per_em / total if total else 1.0


@dataclass(frozen=True)
class TextMeasurer:
    """Largura de texto em pixels do espaco de coordenadas do script ASS (PlayRes)."""

    font_path: Path
    font_size: int
    spacing: float = 0.0

    @classmethod
    def for_style(
        cls, font_name: str, font_size: int, fonts_dir: Path | str, spacing: float = 0.0
    ) -> TextMeasurer:
        return cls(
            font_path=font_file_for(font_name, fonts_dir),
            font_size=font_size,
            spacing=spacing,
        )

    @property
    def em_pixels(self) -> float:
        """Tamanho em que o libass realmente renderiza esta fonte com este `Fontsize`."""
        return self.font_size * em_scale(str(self.font_path))

    def width(self, text: str) -> float:
        if not text:
            return 0.0
        advance = _reference_font(str(self.font_path)).getlength(text)
        # `Spacing` do ASS soma N px DEPOIS de cada glifo, inclusive o ultimo.
        return advance * self.em_pixels / _REFERENCE_EM + self.spacing * len(text)

    @property
    def space_width(self) -> float:
        return self.width(" ")
