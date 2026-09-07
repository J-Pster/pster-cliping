"""Etapa 6: geração e burn-in de legendas estilizadas (ASS/SSA).

`clipador.subtitles.emphasis` NAO e reexportado aqui de proposito: ele e o unico modulo
do pacote que depende do provedor de LLM, e importa-lo aqui obrigaria qualquer uso de
legenda (inclusive teste puro de layout) a carregar o SDK do LLM. Quem precisa da enfase
importa direto do modulo.
"""

from clipador.subtitles.builder import AssSubtitleBuilder, build_ass
from clipador.subtitles.burn import burn_in, save_ass
from clipador.subtitles.cues import Cue, CueRules, CueWord, build_cues
from clipador.subtitles.fonts import BUNDLED_FONTS, DEFAULT_FONTS_DIR, FontNotFoundError, TextMeasurer
from clipador.subtitles.models import HIGHLIGHT_MODES, SubtitleStyle
from clipador.subtitles.presets import (
    DEFAULT_PRESET,
    PRESET_NAMES,
    PRESETS,
    SubtitlePreset,
    build_subtitle_style,
    get_preset,
)

__all__ = [
    "BUNDLED_FONTS",
    "DEFAULT_FONTS_DIR",
    "DEFAULT_PRESET",
    "HIGHLIGHT_MODES",
    "PRESETS",
    "PRESET_NAMES",
    "AssSubtitleBuilder",
    "Cue",
    "CueRules",
    "CueWord",
    "FontNotFoundError",
    "SubtitlePreset",
    "SubtitleStyle",
    "TextMeasurer",
    "build_ass",
    "build_cues",
    "build_subtitle_style",
    "burn_in",
    "get_preset",
    "save_ass",
]
