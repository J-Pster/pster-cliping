"""Estilo configuravel das legendas (.ass): tipografia, geometria, segmentacao e animacao."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clipador.subtitles.cues import CueRules
from clipador.subtitles.fonts import DEFAULT_FONTS_DIR

# Modos de destaque da palavra falada, do mais simples ao mais elaborado:
#
# "sweep"  - karaoke ASS classico com `\kf`: varredura de preenchimento DENTRO da palavra,
#            letra a letra. Um evento por cue. Foi o unico modo ate aqui.
# "switch" - karaoke ASS com `\k`: a palavra inteira troca de cor de uma vez, sem varredura
#            interna. Um evento por cue. Mais proximo do que as ferramentas de clipe fazem
#            hoje, e mais barato de renderizar que "pop".
# "pop"    - um evento POR PALAVRA, com `\pos` calculado a partir da largura medida na
#            fonte real, mais troca de cor e um salto de escala (`\t` + `\fscx/\fscy`) no
#            instante em que a palavra e falada. E o unico modo capaz de animar escala,
#            porque `\k`/`\kf` so sabem interpolar cor.
HIGHLIGHT_MODES = ("sweep", "switch", "pop")

# Alinhamentos ASS (numpad). A faixa define a ancora VERTICAL do bloco de texto:
# 1-3 = base, 4-6 = meio, 7-9 = topo. A coluna define a horizontal: 1/4/7 = esquerda,
# 2/5/8 = centro, 3/6/9 = direita.
_VALID_ALIGNMENTS = range(1, 10)


@dataclass(frozen=True)
class SubtitleStyle:
    """Configuracao visual da legenda ASS. Cores no formato ASS `&HAABBGGRR`.

    Os defaults descrevem o formato CURTO (9:16). O formato longo (16:9) e os demais
    visuais saem de `clipador.subtitles.presets`, que e o ponto de entrada normal - montar
    um `SubtitleStyle` a mao continua valido para ajuste fino pontual.
    """

    # --- tipografia -------------------------------------------------------------------
    # `font_name` precisa casar com a tabela `name` do .ttf embarcado (ver
    # `clipador.subtitles.fonts.BUNDLED_FONTS`), nao com o nome do arquivo.
    font_name: str = "Montserrat ExtraBold"
    fonts_dir: Path = DEFAULT_FONTS_DIR
    # ATENCAO: `Fontsize` do ASS nao e o em da fonte - o libass o converte por
    # `unitsPerEm / (usWinAscent + usWinDescent)` (ver `fonts.em_scale`). Em Montserrat
    # ExtraBold, `184` rende ~86px de altura de caixa alta em 1920, ou seja 4.5% da
    # altura do quadro, que e a faixa usada pelas ferramentas de clipe. O valor anterior
    # (72) rendia ~34px: 1.8% da altura, praticamente ilegivel num telefone.
    font_size: int = 184
    # Falso de proposito: a fonte embarcada JA e ExtraBold/Black. Ligar `Bold` por cima
    # pede negrito sintetico ao libass, que engorda o glifo por transformacao e suja o
    # contorno.
    bold: bool = False
    spacing: float = 0.0

    # --- cores ------------------------------------------------------------------------
    primary_color: str = "&H00FFFFFF"  # branco: palavra ainda nao falada
    highlight_color: str = "&H0000FFFF"  # amarelo: palavra sendo falada agora
    emphasis_color: str = "&H0000E5FF"  # laranja: palavra marcada como enfase pelo LLM
    outline_color: str = "&H00000000"
    # Cor da SOMBRA (campo `BackColour` do ASS com `BorderStyle: 1`). O valor antigo so
    # existia no dataclass: com `shadow=0` o libass nunca desenha sombra, entao a cor era
    # configuracao morta. Agora ha sombra de verdade, que e o que segura a leitura sobre
    # fundo claro.
    shadow_color: str = "&H80000000"
    outline: float = 7.7
    shadow: float = 4.6

    # --- geometria --------------------------------------------------------------------
    alignment: int = 2  # numpad ASS: 2 = centro-inferior (MarginV mede a distancia da base)
    margin_l: int = 56
    margin_r: int = 56
    # 840/1920 ~= 44% da base pra cima: fica um pouco abaixo do centro vertical da tela,
    # fora da faixa inferior (~ultimos 20-25% da altura) onde Instagram/TikTok/Reels
    # sobrepoe legenda-nativa, botoes e comentarios no vertical 9:16. Nao usar valor perto
    # da base (ex.: o antigo 80) nesse formato - fica encoberto ao postar.
    margin_v: int = 840
    play_res_x: int = 1080
    play_res_y: int = 1920
    # Altura de linha como multiplo do EM RENDERIZADO (nao de `font_size`, que e maior que
    # o em - ver `fonts.em_scale`). Usada para posicionar as linhas no modo "pop", que
    # escreve `\pos` de cada palavra e por isso nao herda o entrelinha do libass.
    line_spacing: float = 1.15
    max_lines: int = 2

    # --- segmentacao ------------------------------------------------------------------
    # Teto, nao tamanho fixo: a cue fecha antes disso quando a largura, a duracao, um
    # silencio ou um fim de frase mandam. Ver `clipador.subtitles.cues`.
    max_words_per_cue: int = 6
    min_cue_seconds: float = 0.7
    max_cue_seconds: float = 2.6
    max_gap_seconds: float = 0.6
    hold_seconds: float = 0.35

    # --- texto ------------------------------------------------------------------------
    uppercase: bool = True
    strip_punctuation: bool = True

    # --- animacao ---------------------------------------------------------------------
    highlight_mode: str = "pop"
    fade_in_ms: int = 70
    fade_out_ms: int = 70
    # Escala (em % do tamanho normal) do salto da palavra ativa e da palavra de enfase.
    pop_scale: int = 112
    emphasis_scale: int = 124
    pop_ms: int = 110
    # Falso = so a palavra falada AGORA fica destacada e as anteriores voltam ao branco
    # (visual das ferramentas de clipe atuais). Verdadeiro = karaoke classico, o destaque
    # acumula ate o fim da cue.
    highlight_persists: bool = False

    def __post_init__(self) -> None:
        if self.highlight_mode not in HIGHLIGHT_MODES:
            raise ValueError(
                f"highlight_mode invalido: {self.highlight_mode!r}. Validos: {HIGHLIGHT_MODES}"
            )
        if self.alignment not in _VALID_ALIGNMENTS:
            raise ValueError(f"alignment invalido: {self.alignment!r}. Valido: 1..9")
        if self.max_lines < 1:
            raise ValueError(f"max_lines precisa ser >= 1, veio {self.max_lines}")
        if self.max_words_per_cue < 1:
            raise ValueError(f"max_words_per_cue precisa ser >= 1, veio {self.max_words_per_cue}")
        if self.min_cue_seconds > self.max_cue_seconds:
            raise ValueError(
                f"min_cue_seconds ({self.min_cue_seconds}) nao pode passar de "
                f"max_cue_seconds ({self.max_cue_seconds})"
            )
        if self.usable_width <= 0:
            raise ValueError(
                f"Margens ({self.margin_l}+{self.margin_r}) nao deixam largura util em "
                f"play_res_x={self.play_res_x}"
            )

    @property
    def usable_width(self) -> float:
        """Largura disponivel pra uma linha de legenda, em px do espaco do PlayRes."""
        return self.play_res_x - self.margin_l - self.margin_r

    @property
    def layout_width(self) -> float:
        """Largura util descontando o espaco que o salto de escala do modo "pop" ocupa.

        No modo "pop" a palavra ativa cresce `pop_scale`% e os vaos entre palavras
        reservam metade desse crescimento de cada lado (ver `builder._pop_gap`). Se o
        agrupamento usasse a largura util cheia, quase toda cue estouraria no layout e
        seria condensada pelo `fit` - condensacao que deve ficar reservada para a palavra
        que realmente nao cabe, nao virar o caso comum.
        """
        if self.highlight_mode != "pop":
            return self.usable_width
        return self.usable_width / (1 + max(0, self.pop_scale - 100) / 200)

    def cue_rules(self) -> CueRules:
        return CueRules(
            max_line_width=self.layout_width,
            max_lines=self.max_lines,
            max_words=self.max_words_per_cue,
            min_seconds=self.min_cue_seconds,
            max_seconds=self.max_cue_seconds,
            max_gap_seconds=self.max_gap_seconds,
            hold_seconds=self.hold_seconds,
            uppercase=self.uppercase,
            strip_punctuation=self.strip_punctuation,
        )
