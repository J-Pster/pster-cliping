"""Gerador do conteudo .ass a partir do timestamp por palavra da transcricao.

Tres modos de destaque, escolhidos por `SubtitleStyle.highlight_mode` (ver
`clipador.subtitles.models`):

`sweep` e `switch` usam o karaoke NATIVO do ASS (`\\kf` e `\\k`), um evento `Dialogue`
por cue. O destaque de cor nao usa override manual: e a combinacao `\\k*` +
`PrimaryColour`/`SecondaryColour` do estilo, o mecanismo consagrado do formato, que o
proprio libass sincroniza. Por convencao do ASS, `PrimaryColour` e a cor da porcao ja
"cantada" (aqui: a palavra destacada) e `SecondaryColour` a da porcao ainda nao
alcancada (aqui: a palavra ainda nao falada) - por isso `highlight_color`/`primary_color`
do estilo sao mapeados CRUZADOS para `primarycolor`/`secondarycolor` do `SSAStyle`.

`pop` (default) sai desse caminho de proposito: emite um evento POR PALAVRA com `\\pos`
explicito. Foi a unica forma de animar ESCALA, que e o que separa o visual atual das
ferramentas de clipe do karaoke de cor puro - `\\k`/`\\kf` so interpolam cor, nunca
`\\fscx/\\fscy`. O custo e ter que calcular a posicao de cada palavra em vez de deixar o
libass diagramar; a largura vem de `clipador.subtitles.fonts.TextMeasurer`, medida no
MESMO .ttf embarcado que o libass usa. Como toda palavra vai posicionada, o libass nao
refaz layout nenhum: nao ha divergencia possivel entre o que foi medido e o que e
renderizado.

A quebra de linha e sempre nossa (`\\N` no texto, `WrapStyle: 2`), nunca automatica: ver
o cabecalho de `clipador.subtitles.cues` para o porque.

`pysubs2` e usado so como camada de serializacao/IO (`SSAFile`/`SSAStyle`/`SSAEvent`).
"""

from __future__ import annotations

from collections.abc import Sequence

import pysubs2

from clipador.subtitles.cues import Cue, CueWord, build_cues
from clipador.subtitles.fonts import TextMeasurer
from clipador.subtitles.models import SubtitleStyle
from clipador.transcribe.models import Word

_KARAOKE_TAG = {"sweep": "kf", "switch": "k"}


def _parse_ass_color(value: str) -> pysubs2.Color:
    """Converte cor no formato ASS `&HAABBGGRR` em `pysubs2.Color`."""
    hex_digits = value.upper().removeprefix("&H").removesuffix("&").rjust(8, "0")
    alpha, blue, green, red = (int(hex_digits[i : i + 2], 16) for i in range(0, 8, 2))
    return pysubs2.Color(r=red, g=green, b=blue, a=alpha)


def _override_color(value: str) -> str:
    """Forma da cor aceita pelas tags de override (`\\1c`, `\\3c`): `&HBBGGRR&`, SEM alfa.

    O alfa vive em tags separadas (`\\1a`/`\\3a`); mandar os 8 digitos do formato de
    estilo aqui faz o libass ler o par errado de canais e a cor sai trocada."""
    hex_digits = value.upper().removeprefix("&H").removesuffix("&").rjust(8, "0")
    return f"&H{hex_digits[2:]}&"


def _escape_text(text: str) -> str:
    return text.replace("{", r"\{").replace("}", r"\}")


def _cs(seconds: float) -> int:
    """Centisegundos, unidade nativa das tags `\\k`/`\\kf`."""
    return max(0, round(seconds * 100))


def _ms(seconds: float) -> int:
    """Milissegundos, unidade nativa da tag `\\t` (sempre relativa ao inicio do evento)."""
    return max(0, round(seconds * 1000))


def _build_style(style: SubtitleStyle) -> pysubs2.SSAStyle:
    karaoke = style.highlight_mode in _KARAOKE_TAG
    # No modo "pop" nao ha karaoke: a cor base tem que ser a PrimaryColour, porque e sobre
    # ela que os overrides `\1c` por palavra trabalham.
    primary = style.highlight_color if karaoke else style.primary_color
    secondary = style.primary_color if karaoke else style.highlight_color
    return pysubs2.SSAStyle(
        fontname=style.font_name,
        fontsize=style.font_size,
        primarycolor=_parse_ass_color(primary),
        secondarycolor=_parse_ass_color(secondary),
        outlinecolor=_parse_ass_color(style.outline_color),
        backcolor=_parse_ass_color(style.shadow_color),
        bold=style.bold,
        outline=style.outline,
        shadow=style.shadow,
        spacing=style.spacing,
        alignment=pysubs2.Alignment(style.alignment),
        marginl=style.margin_l,
        marginr=style.margin_r,
        marginv=style.margin_v,
    )


# Piso da compressao horizontal automatica. Abaixo disso a fonte deixa de parecer
# condensada e passa a parecer deformada; melhor deixar transbordar e avisar.
MIN_FIT_SCALE = 70


def fit_scale(cue: Cue, style: SubtitleStyle, space_width: float) -> int:
    """Escala horizontal (em %) que faz a linha mais larga da cue caber na largura util.

    Palavra longa e regra em PT-BR, nao excecao ("improrrogaveis", "classificacao"), e uma
    unica palavra pode estourar a largura sozinha - caso em que nenhuma quebra de linha
    resolve. Condensar SO na horizontal (`\\fscx`, sem tocar em `\\fscy`) e o que legenda de
    TV faz nessa situacao: mantem a altura da linha e o grid vertical, e ate ~15% de
    condensacao passa despercebido numa fonte display pesada.
    """
    widest = max(
        (sum(word.width for word in line) + space_width * (len(line) - 1) for line in cue.lines),
        default=0.0,
    )
    if widest <= style.usable_width or widest <= 0:
        return 100
    return max(MIN_FIT_SCALE, int(style.usable_width / widest * 100))


def _fade_tag(style: SubtitleStyle) -> str:
    if style.fade_in_ms <= 0 and style.fade_out_ms <= 0:
        return ""
    return f"\\fad({max(0, style.fade_in_ms)},{max(0, style.fade_out_ms)})"


def _karaoke_cue_text(cue: Cue, style: SubtitleStyle, fit: int = 100) -> str:
    """Texto do evento com um bloco `{\\k}`/`{\\kf}` por palavra (e por silencio entre
    palavras), com a quebra de linha ja resolvida em `\\N`."""
    tag = _KARAOKE_TAG[style.highlight_mode]
    prefix = _fade_tag(style) + (f"\\fscx{fit}" if fit != 100 else "")
    parts: list[str] = [f"{{{prefix}}}"] if prefix else []
    cursor = cue.start
    last_line = len(cue.lines) - 1
    for line_index, line in enumerate(cue.lines):
        last_word = len(line) - 1
        for word_index, word in enumerate(line):
            gap_cs = _cs(word.start - cursor)
            if gap_cs > 0:
                parts.append(f"{{\\{tag}{gap_cs}}}")
            if word_index < last_word:
                suffix = " "
            elif line_index < last_line:
                suffix = "\\N"
            else:
                suffix = ""
            body = _escape_text(word.text)
            if word.emphasis:
                # Enfase nos modos de karaoke muda o CONTORNO, nao o preenchimento: o
                # preenchimento pertence ao mecanismo `\k` (primary/secondary) e um
                # override `\1c` no meio dele mataria a troca de cor da palavra.
                body = f"{{\\3c{_override_color(style.emphasis_color)}}}{body}{{\\3c{_override_color(style.outline_color)}}}"
            parts.append(f"{{\\{tag}{_cs(word.end - word.start)}}}{body}{suffix}")
            cursor = word.end
    return "".join(parts)


def _line_x_start(line_width: float, style: SubtitleStyle) -> float:
    column = (style.alignment - 1) % 3
    if column == 0:
        return float(style.margin_l)
    if column == 2:
        return style.play_res_x - style.margin_r - line_width
    return (style.play_res_x - line_width) / 2


def _block_top(line_count: int, style: SubtitleStyle, line_height: float) -> float:
    """Topo do bloco de texto, derivado da faixa vertical do `alignment` do estilo.

    O modo "pop" posiciona cada palavra com `\\pos`, entao ele mesmo precisa reproduzir a
    conta que o libass faria com `MarginV` + `Alignment`, senao a legenda animada ficaria
    numa altura diferente da dos outros modos.
    """
    block_height = line_count * line_height
    band = (style.alignment - 1) // 3  # 0 = base, 1 = meio, 2 = topo
    if band == 0:
        return style.play_res_y - style.margin_v - block_height
    if band == 2:
        return float(style.margin_v)
    return (style.play_res_y - block_height) / 2


def _pop_word_text(
    word: CueWord,
    cue: Cue,
    x_center: float,
    y_center: float,
    style: SubtitleStyle,
    fit: int = 100,
) -> str:
    base_color = style.emphasis_color if word.emphasis else style.primary_color
    active_color = style.emphasis_color if word.emphasis else style.highlight_color
    pop = style.emphasis_scale if word.emphasis else style.pop_scale
    # A condensacao horizontal da cue e o repouso da animacao, nao 100: sem isso a palavra
    # voltaria do salto na largura cheia e estouraria a linha que o `fit` corrigiu.
    pop_x = round(fit * pop / 100)

    grow_start = _ms(word.start - cue.start)
    grow_end = grow_start + max(1, style.pop_ms)
    shrink_end = grow_end + max(1, style.pop_ms)

    tags = [
        "\\an5",
        f"\\pos({x_center:.0f},{y_center:.0f})",
        _fade_tag(style),
        f"\\fscx{fit}" if fit != 100 else "",
        f"\\1c{_override_color(base_color)}",
        f"\\t({grow_start},{grow_end},\\fscx{pop_x}\\fscy{pop}\\1c{_override_color(active_color)})",
        f"\\t({grow_end},{shrink_end},\\fscx{fit}\\fscy100)",
    ]
    if not style.highlight_persists and not word.emphasis:
        release_start = max(shrink_end, _ms(word.end - cue.start))
        release_end = release_start + max(1, style.pop_ms)
        tags.append(
            f"\\t({release_start},{release_end},\\1c{_override_color(style.primary_color)})"
        )
    return f"{{{''.join(tag for tag in tags if tag)}}}{_escape_text(word.text)}"


def _pop_gap(left: CueWord, right: CueWord, style: SubtitleStyle, space_width: float) -> float:
    """Vao entre duas palavras vizinhas, ja reservando o espaco do salto de escala.

    A palavra ativa cresce `pop_scale`% em torno do PROPRIO centro, ou seja invade metade
    do crescimento para cada lado. Com o vao igual a um espaco normal, ela encosta na
    vizinha no auge do salto - o defeito visual mais obvio do modo "pop". Reservar
    (crescimento_esquerda + crescimento_direita)/2 elimina a colisao por construcao, em
    vez de depender de o salto ser pequeno o bastante.
    """
    def growth(word: CueWord) -> float:
        scale = style.emphasis_scale if word.emphasis else style.pop_scale
        return word.width * max(0, scale - 100) / 100

    return space_width + (growth(left) + growth(right)) / 2


def _pop_line_width(
    line: Sequence[CueWord], style: SubtitleStyle, space_width: float
) -> float:
    return sum(word.width for word in line) + sum(
        _pop_gap(line[i], line[i + 1], style, space_width) for i in range(len(line) - 1)
    )


def _pop_fit_scale(cue: Cue, style: SubtitleStyle, space_width: float) -> int:
    """`fit_scale` do modo pop: mede a linha com os vaos do salto ja reservados."""
    widest = max((_pop_line_width(line, style, space_width) for line in cue.lines), default=0.0)
    if widest <= style.usable_width or widest <= 0:
        return 100
    return max(MIN_FIT_SCALE, int(style.usable_width / widest * 100))


def _pop_events(
    cue: Cue, style: SubtitleStyle, measurer: TextMeasurer
) -> list[pysubs2.SSAEvent]:
    events: list[pysubs2.SSAEvent] = []
    space_width = measurer.space_width
    # O entrelinha acompanha o EM RENDERIZADO, nao o `font_size` do estilo: como
    # `Fontsize` do ASS e maior que o em (ver `fonts.em_scale`), usar `font_size` aqui
    # abriria um vao entre as linhas quase o dobro do correto.
    line_height = style.line_spacing * measurer.em_pixels
    top = _block_top(len(cue.lines), style, line_height)
    fit = _pop_fit_scale(cue, style, space_width)
    factor = fit / 100

    for line_index, line in enumerate(cue.lines):
        # As larguras usadas pra posicionar sao as JA condensadas: `\fscx` muda o avanco
        # real do glifo, entao posicionar pela largura nominal deslocaria toda a linha.
        line_width = _pop_line_width(line, style, space_width) * factor
        cursor = _line_x_start(line_width, style)
        y_center = top + line_height * (line_index + 0.5)
        for index, word in enumerate(line):
            width = word.width * factor
            events.append(
                pysubs2.SSAEvent(
                    start=round(cue.start * 1000),
                    end=round(cue.end * 1000),
                    style="Default",
                    text=_pop_word_text(word, cue, cursor + width / 2, y_center, style, fit),
                )
            )
            cursor += width
            if index + 1 < len(line):
                cursor += _pop_gap(word, line[index + 1], style, space_width) * factor
    return events


class AssSubtitleBuilder:
    """Segmenta as palavras em cues e monta o documento .ass via pysubs2."""

    def __init__(self, style: SubtitleStyle = SubtitleStyle()) -> None:
        self.style = style

    @staticmethod
    def _measurer(style: SubtitleStyle) -> TextMeasurer:
        return TextMeasurer.for_style(
            style.font_name, style.font_size, style.fonts_dir, style.spacing
        )

    def cues(
        self,
        words: Sequence[Word],
        style: SubtitleStyle | None = None,
        emphasis_word_ids: frozenset[int] = frozenset(),
    ) -> list[Cue]:
        style = style or self.style
        return build_cues(words, style.cue_rules(), self._measurer(style), emphasis_word_ids)

    def build_subs(
        self,
        words: Sequence[Word],
        style: SubtitleStyle | None = None,
        emphasis_word_ids: frozenset[int] = frozenset(),
    ) -> pysubs2.SSAFile:
        """`style` sobrescreve o estilo construido pra esta chamada (ex.: 16:9 pro formato
        longo em vez do 9:16 default), sem alterar `self.style` pras proximas chamadas."""
        style = style or self.style
        measurer = self._measurer(style)

        subs = pysubs2.SSAFile()
        subs.info["Title"] = "Clipador Subtitles"
        # "None" = as cores do estilo vao para o renderizador como RGB literal, sem
        # conversao de espaco de cor. O valor anterior ("TV.601") declarava que as cores
        # estavam em BT.601 e autorizava o libass a reconverte-las para o espaco do
        # video; hoje isso acerta porque o burn-in e sempre BT.601, mas passa a errar a
        # crominancia dos destaques no dia em que o pipeline gerar HD/BT.709.
        subs.info["YCbCr Matrix"] = "None"
        subs.info["PlayResX"] = str(style.play_res_x)
        subs.info["PlayResY"] = str(style.play_res_y)
        # 2 = "sem quebra automatica, so onde houver \N". A quebra ja foi decidida com a
        # largura real medida; deixar o libass quebrar de novo mudaria o numero de linhas
        # e a altura do bloco de cue pra cue.
        subs.info["WrapStyle"] = "2"
        subs.info["ScaledBorderAndShadow"] = "yes"
        subs.styles["Default"] = _build_style(style)

        for cue in build_cues(words, style.cue_rules(), measurer, emphasis_word_ids):
            if style.highlight_mode == "pop":
                subs.events.extend(_pop_events(cue, style, measurer))
                continue
            subs.events.append(
                pysubs2.SSAEvent(
                    start=round(cue.start * 1000),
                    end=round(cue.end * 1000),
                    style="Default",
                    text=_karaoke_cue_text(
                        cue, style, fit_scale(cue, style, measurer.space_width)
                    ),
                )
            )
        return subs

    def build(
        self,
        words: Sequence[Word],
        style: SubtitleStyle | None = None,
        emphasis_word_ids: frozenset[int] = frozenset(),
    ) -> str:
        return self.build_subs(words, style, emphasis_word_ids).to_string("ass")


def build_ass(
    words: list[Word],
    style: SubtitleStyle = SubtitleStyle(),
    emphasis_word_ids: frozenset[int] = frozenset(),
) -> str:
    return AssSubtitleBuilder(style).build(words, emphasis_word_ids=emphasis_word_ids)
