"""Presets visuais de legenda, por nome, resolvidos por formato de clipe.

Separacao deliberada entre duas coisas que antes viviam misturadas no mesmo dataclass:

- GEOMETRIA e uma funcao do FORMATO. Resolucao do script, margens e o tamanho de fonte
  RELATIVO a altura do quadro saem de `_GEOMETRY_BY_FORMAT`. E aqui que mora a correcao
  do peso da legenda no vertical, que era proporcionalmente quase metade da do horizontal
  (ver comentario em `SubtitleStyle.font_size`).
- LOOK e uma escolha editorial. Fonte, paleta, caixa alta, espessura de contorno e modo
  de animacao saem do preset escolhido na CLI (`--subtitle-preset`).

O tamanho de fonte e guardado como FRACAO DA ALTURA e so vira pixel no cruzamento
preset x formato. Guardar em pixel foi exatamente o que produziu o bug de inversao: o
mesmo `72` significa 3.75% da altura em 1920 e 6.7% em 1080.
"""

from __future__ import annotations

from dataclasses import dataclass

from clipador.select.models import CLIP_FORMATS, LONG_FORMAT, SHORT_FORMAT
from clipador.subtitles.models import SubtitleStyle


@dataclass(frozen=True)
class _Geometry:
    play_res_x: int
    play_res_y: int
    margin_l: int
    margin_r: int
    margin_v: int
    max_lines: int
    # Multiplicador aplicado sobre o `font_size_ratio` do preset. O ratio e calibrado no
    # vertical (1920 de altura); no horizontal a mesma fracao daria um corpo pequeno
    # demais, porque a altura do quadro e quase metade - dai o fator > 1.
    font_scale: float


_GEOMETRY_BY_FORMAT: dict[str, _Geometry] = {
    # margin_v 658 poe a BASE do bloco de 2 linhas em y=1262 (66% da altura), com o centro
    # do bloco em ~60%: um pouco abaixo do meio da tela, como pedido, e ainda com 318px de
    # folga ate o limite mais apertado das plataformas.
    #
    # Faixa de UI que come o rodape no 9:16 (valores de trabalho, conferir quando o app
    # mudar de layout): TikTok ~340px (legenda + @ + faixa de musica), Instagram Reels
    # ~320px, YouTube Shorts ~250px. O mais restritivo manda: nada de legenda abaixo de
    # y=1580.
    SHORT_FORMAT: _Geometry(
        play_res_x=1080,
        play_res_y=1920,
        margin_l=56,
        margin_r=56,
        margin_v=658,
        max_lines=2,
        font_scale=1.0,
    ),
    # No player do YouTube nao ha UI sobreposta no meio do quadro, entao vale a posicao
    # tradicional de legenda, perto da base.
    LONG_FORMAT: _Geometry(
        play_res_x=1920,
        play_res_y=1080,
        margin_l=180,
        margin_r=180,
        margin_v=90,
        max_lines=2,
        # Mantido em 1.06 de proposito. A tentacao ao reduzir o ratio dos presets foi subir
        # este fator pra deixar o formato longo inalterado, ja que o pedido de diminuir era
        # sobre o vertical. Isso reintroduzia a INVERSAO que
        # `test_legenda_do_vertical_pesa_mais_que_a_do_horizontal_em_fracao_de_altura`
        # existe pra impedir: o vertical passaria a pesar menos que o horizontal em fracao
        # da altura, e ele e justamente o que se assiste no celular, muitas vezes sem som.
        font_scale=1.06,
    ),
}


@dataclass(frozen=True)
class SubtitlePreset:
    """Look da legenda, independente do formato do clipe."""

    name: str
    description: str
    font_name: str
    # `Fontsize` do ASS como fracao da altura do quadro, antes do `font_scale` do formato.
    # E especifico da FONTE do preset: `Fontsize` nao e o em (ver `fonts.em_scale`) e cada
    # fonte rende uma altura de caixa alta diferente pro mesmo numero. Os valores abaixo
    # foram calibrados medindo o render real do libass. Alvo: caixa alta em ~3.7% da altura
    # do quadro no formato curto. A calibragem anterior mirava ~4.5%, copiando as
    # ferramentas de clipe, mas elas mostram 1-3 palavras curtas sobre um rosto falando;
    # com palavra longa em portugues e plano estatico, aquele peso comia quadro demais e
    # ainda forcava condensacao horizontal em palavra como "improrrogaveis".
    font_size_ratio: float
    highlight_color: str
    emphasis_color: str
    primary_color: str = "&H00FFFFFF"
    outline_color: str = "&H00000000"
    shadow_color: str = "&H80000000"
    outline_ratio: float = 0.042  # espessura do contorno como fracao do font_size
    shadow_ratio: float = 0.025
    uppercase: bool = True
    strip_punctuation: bool = True
    highlight_mode: str = "pop"
    highlight_persists: bool = False
    pop_scale: int = 112
    emphasis_scale: int = 124
    max_words_per_cue: int = 6

    def style_for(self, clip_format: str) -> SubtitleStyle:
        geometry = _GEOMETRY_BY_FORMAT.get(clip_format)
        if geometry is None:
            raise ValueError(
                f"Formato de clipe desconhecido: {clip_format!r}. Validos: {CLIP_FORMATS}"
            )
        font_size = round(geometry.play_res_y * self.font_size_ratio * geometry.font_scale)
        return SubtitleStyle(
            font_name=self.font_name,
            font_size=font_size,
            primary_color=self.primary_color,
            highlight_color=self.highlight_color,
            emphasis_color=self.emphasis_color,
            outline_color=self.outline_color,
            shadow_color=self.shadow_color,
            outline=round(font_size * self.outline_ratio, 1),
            shadow=round(font_size * self.shadow_ratio, 1),
            margin_l=geometry.margin_l,
            margin_r=geometry.margin_r,
            margin_v=geometry.margin_v,
            play_res_x=geometry.play_res_x,
            play_res_y=geometry.play_res_y,
            max_lines=geometry.max_lines,
            max_words_per_cue=self.max_words_per_cue,
            uppercase=self.uppercase,
            strip_punctuation=self.strip_punctuation,
            highlight_mode=self.highlight_mode,
            highlight_persists=self.highlight_persists,
            pop_scale=self.pop_scale,
            emphasis_scale=self.emphasis_scale,
        )


PRESETS: dict[str, SubtitlePreset] = {
    preset.name: preset
    for preset in (
        SubtitlePreset(
            name="impacto",
            description=(
                "Montserrat ExtraBold, caixa alta, branco com a palavra falada em amarelo "
                "e salto de escala. Look de ferramenta de clipe moderna; default."
            ),
            font_name="Montserrat ExtraBold",
            font_size_ratio=0.078,
            highlight_color="&H0000FFFF",
            emphasis_color="&H0000E5FF",
        ),
        SubtitlePreset(
            name="anton",
            description=(
                "Anton condensada, caixa alta, destaque verde. A condensacao cabe mais "
                "palavra por linha - util em PT-BR, que tem palavra longa."
            ),
            font_name="Anton",
            font_size_ratio=0.0715,
            highlight_color="&H0076E600",
            emphasis_color="&H00FFD400",
        ),
        SubtitlePreset(
            name="neon",
            description=(
                "Archivo Black com contorno grosso e destaque magenta. Contraste alto "
                "para clipe com fundo claro ou muito ruidoso."
            ),
            font_name="Archivo Black",
            font_size_ratio=0.0674,
            highlight_color="&H00E526FF",
            emphasis_color="&H0000FFFF",
            outline_ratio=0.056,
            shadow_ratio=0.015,
        ),
        SubtitlePreset(
            name="classico",
            description=(
                "Karaoke tradicional: caixa mista, pontuacao preservada, varredura de cor "
                "sem animacao de escala. Mais sobrio, para conteudo longo e formal."
            ),
            font_name="Montserrat ExtraBold",
            font_size_ratio=0.0626,
            highlight_color="&H0000FFFF",
            emphasis_color="&H0000E5FF",
            uppercase=False,
            strip_punctuation=False,
            highlight_mode="switch",
            highlight_persists=True,
            max_words_per_cue=8,
        ),
    )
}

PRESET_NAMES = tuple(PRESETS)
DEFAULT_PRESET = "impacto"


def get_preset(name: str) -> SubtitlePreset:
    preset = PRESETS.get(name)
    if preset is None:
        raise ValueError(f"Preset de legenda desconhecido: {name!r}. Validos: {PRESET_NAMES}")
    return preset


def build_subtitle_style(preset_name: str, clip_format: str) -> SubtitleStyle:
    return get_preset(preset_name).style_for(clip_format)
