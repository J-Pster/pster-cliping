"""Segmentacao das palavras em cues e quebra de linha deterministica.

Substitui o fatiamento em janelas fixas de N palavras, que era cego para tres coisas que
decidem a legibilidade de uma legenda queimada:

1. LARGURA REAL. Cinco palavras podem ser 18 ou 52 caracteres. Com janela fixa, o libass
   quebrava sozinho (`WrapStyle: 0`) e o bloco de texto mudava de altura a cada cue -
   a legenda "pulava" na tela. Aqui a quebra e calculada em PIXELS medidos na fonte real
   e escrita no evento com `\\N`, entao o layout e o mesmo que foi decidido aqui.
2. FRONTEIRA DE FRASE. Janela fixa corta no meio do sintagma ("...Trinta / dias em..."),
   o que quebra a leitura. Aqui a cue fecha preferencialmente em pontuacao terminal.
3. DURACAO. Cinco palavras com silencio no meio viram uma cue de 4s parada na tela.
   Aqui ha teto de duracao e corte em silencio longo.

O agrupamento nao usa orcamento de caracteres como heuristica: ele TENTA a quebra de
linha a cada palavra e so aceita a palavra se o conjunto ainda couber em `max_lines`
linhas de ate `max_line_width` pixels. E exato, e o mesmo codigo que produz o layout
final, entao nao existe divergencia entre "cabia na conta" e "coube no render".
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from clipador.subtitles.fonts import TextMeasurer
from clipador.transcribe.models import Word

logger = logging.getLogger(__name__)

TERMINAL_PUNCTUATION = ".!?…"
# Removida das pontas quando `strip_punctuation` esta ligado. Hifen e apostrofo ficam:
# sao parte de palavra em PT-BR ("bem-vindo", "d'agua"), nao pontuacao de frase.
_STRIPPABLE = ".,;:!?…\"'“”‘’()[]{}«»"
_CLOSING_MARKS = "\"'“”‘’)]}»"


@dataclass(frozen=True)
class CueWord:
    """Palavra pronta pra render: texto final, tempo e largura ja medida."""

    text: str
    start: float
    end: float
    width: float
    ends_sentence: bool = False
    emphasis: bool = False


@dataclass(frozen=True)
class Cue:
    """Bloco de legenda: linhas ja quebradas + janela de exibicao na tela.

    `start`/`end` sao a janela do EVENTO, que pode ser maior que o span das palavras
    (ver `CueRules.hold_seconds`): sem isso a legenda pisca no silencio entre cues.
    """

    lines: tuple[tuple[CueWord, ...], ...]
    start: float
    end: float

    @property
    def words(self) -> tuple[CueWord, ...]:
        return tuple(word for line in self.lines for word in line)


@dataclass(frozen=True)
class CueRules:
    max_line_width: float
    max_lines: int = 2
    max_words: int = 6
    min_seconds: float = 0.7
    max_seconds: float = 2.6
    max_gap_seconds: float = 0.6
    hold_seconds: float = 0.35
    uppercase: bool = True
    strip_punctuation: bool = True


def render_text(raw: str, *, uppercase: bool, strip_punctuation: bool) -> str:
    """Texto da palavra como ele vai aparecer na tela."""
    text = raw.strip()
    if strip_punctuation:
        text = text.strip(_STRIPPABLE)
    return text.upper() if uppercase else text


def ends_sentence(raw: str) -> bool:
    stripped = raw.strip().rstrip(_CLOSING_MARKS)
    return bool(stripped) and stripped[-1] in TERMINAL_PUNCTUATION


def build_cue_words(
    words: Sequence[Word],
    rules: CueRules,
    measurer: TextMeasurer,
    emphasis_word_ids: frozenset[int] = frozenset(),
) -> list[CueWord]:
    """Converte `Word` da transcricao em `CueWord` renderizavel, descartando o que
    ficaria vazio na tela (ex.: token so de pontuacao que sobrou da normalizacao)."""
    result: list[CueWord] = []
    for word in words:
        text = render_text(
            word.text, uppercase=rules.uppercase, strip_punctuation=rules.strip_punctuation
        )
        if not text:
            continue
        result.append(
            CueWord(
                text=text,
                start=word.start,
                end=max(word.end, word.start),
                width=measurer.width(text),
                ends_sentence=ends_sentence(word.text),
                emphasis=word.id in emphasis_word_ids,
            )
        )
    return result


def _line_width(words: Sequence[CueWord], first: int, last: int, space_width: float) -> float:
    return sum(w.width for w in words[first : last + 1]) + space_width * (last - first)


def split_into_lines(
    words: Sequence[CueWord], line_count: int, space_width: float
) -> tuple[tuple[int, ...], float]:
    """Divide `words` em exatamente `line_count` linhas nao vazias MINIMIZANDO a largura
    da linha mais larga (minimax). Devolve os indices de inicio de cada linha e a largura
    da maior. Minimax em vez de guloso porque o resultado e visualmente equilibrado: duas
    linhas parecidas em vez de uma cheia e uma com uma palavra sobrando."""
    total = len(words)
    if line_count < 1 or line_count > total:
        raise ValueError(f"line_count invalido: {line_count} para {total} palavra(s)")

    @lru_cache(maxsize=None)
    def best(start: int, lines_left: int) -> tuple[float, tuple[int, ...]]:
        if lines_left == 1:
            return _line_width(words, start, total - 1, space_width), ()
        chosen: tuple[float, tuple[int, ...]] | None = None
        # A primeira linha vai de `start` ate `cut-1`; o resto precisa sobrar pelo menos
        # uma palavra por linha restante.
        for cut in range(start + 1, total - lines_left + 2):
            head = _line_width(words, start, cut - 1, space_width)
            tail, tail_cuts = best(cut, lines_left - 1)
            candidate = (max(head, tail), (cut, *tail_cuts))
            if chosen is None or candidate[0] < chosen[0]:
                chosen = candidate
        assert chosen is not None
        return chosen

    widest, cuts = best(0, line_count)
    best.cache_clear()
    return (0, *cuts), widest


def wrap(
    words: Sequence[CueWord], rules: CueRules, space_width: float
) -> tuple[tuple[CueWord, ...], ...] | None:
    """Menor numero de linhas em que `words` cabe respeitando `max_line_width`.
    `None` quando nao cabe em `max_lines` linhas."""
    if not words:
        return None
    for line_count in range(1, min(rules.max_lines, len(words)) + 1):
        starts, widest = split_into_lines(words, line_count, space_width)
        if widest <= rules.max_line_width:
            bounds = (*starts[1:], len(words))
            return tuple(
                tuple(words[start:end]) for start, end in zip(starts, bounds, strict=True)
            )
    return None


def _force_wrap(
    words: Sequence[CueWord], rules: CueRules, space_width: float
) -> tuple[tuple[CueWord, ...], ...]:
    """Layout de uma cue que nao cabe nem na melhor quebra: palavra unica larga demais
    pro quadro. Nao ha o que quebrar, entao a cue sai assim mesmo e o builder condensa
    horizontalmente na hora do render (ver `subtitles.builder.fit_scale`)."""
    line_count = min(rules.max_lines, len(words))
    starts, widest = split_into_lines(words, line_count, space_width)
    logger.debug(
        "Cue mais larga que a area util (%.0fpx > %.0fpx), sera condensada: %s",
        widest,
        rules.max_line_width,
        " ".join(w.text for w in words),
    )
    bounds = (*starts[1:], len(words))
    return tuple(tuple(words[start:end]) for start, end in zip(starts, bounds, strict=True))


def _duration(group: Sequence[CueWord]) -> float:
    return group[-1].end - group[0].start


def _must_break_before(group: Sequence[CueWord], word: CueWord, rules: CueRules) -> bool:
    return (
        len(group) >= rules.max_words
        or word.start - group[-1].end > rules.max_gap_seconds
        or word.end - group[0].start > rules.max_seconds
    )


def _group_words(
    words: Sequence[CueWord], rules: CueRules, space_width: float
) -> list[list[CueWord]]:
    groups: list[list[CueWord]] = []
    current: list[CueWord] = []
    for word in words:
        if current and _must_break_before(current, word, rules):
            groups.append(current)
            current = []
        if current and wrap([*current, word], rules, space_width) is None:
            groups.append(current)
            current = []
        current.append(word)
        # Fecha em fim de frase, mas so quando a cue ja tem tempo de tela suficiente -
        # senao um "Sim." isolado viraria uma cue de 300ms piscando.
        if word.ends_sentence and _duration(current) >= rules.min_seconds:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _can_join(
    left: Sequence[CueWord], right: Sequence[CueWord], rules: CueRules, space_width: float
) -> bool:
    joined = [*left, *right]
    return (
        len(joined) <= rules.max_words
        and right[0].start - left[-1].end <= rules.max_gap_seconds
        and _duration(joined) <= rules.max_seconds
        and wrap(joined, rules, space_width) is not None
    )


def _merge_short_groups(
    groups: list[list[CueWord]], rules: CueRules, space_width: float
) -> list[list[CueWord]]:
    """Absorve cue curta demais na vizinha, quando a juncao ainda respeita todos os
    limites. Sem isso sobra cue orfa de 1 palavra no fim de cada frase."""
    merged: list[list[CueWord]] = []
    for group in groups:
        if (
            merged
            and _duration(group) < rules.min_seconds
            and _can_join(merged[-1], group, rules, space_width)
        ):
            merged[-1] = [*merged[-1], *group]
            continue
        merged.append(list(group))
    return merged


def build_cues(
    words: Sequence[Word],
    rules: CueRules,
    measurer: TextMeasurer,
    emphasis_word_ids: frozenset[int] = frozenset(),
) -> list[Cue]:
    """Pipeline completo: renderiza o texto, agrupa em cues e quebra cada uma em linhas."""
    space_width = measurer.space_width
    cue_words = build_cue_words(words, rules, measurer, emphasis_word_ids)
    if not cue_words:
        return []

    groups = _merge_short_groups(_group_words(cue_words, rules, space_width), rules, space_width)

    cues: list[Cue] = []
    for index, group in enumerate(groups):
        lines = wrap(group, rules, space_width) or _force_wrap(group, rules, space_width)
        end = group[-1].end + rules.hold_seconds
        next_start = groups[index + 1][0].start if index + 1 < len(groups) else None
        if next_start is not None:
            end = min(end, next_start)
        cues.append(Cue(lines=lines, start=group[0].start, end=max(end, group[-1].end)))
    return cues
