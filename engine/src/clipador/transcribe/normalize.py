"""Normalizacao da transcricao crua, entre o ASR e todo o resto do pipeline.

O ASR devolve tokens, nao palavras prontas pra tela. Quatro defeitos aparecem em toda
transcricao real e todos chegavam intactos na legenda queimada:

1. SIGLA ESTILHACADA. "GAECO" volta como `G` `.A` `.E` `.C` `.O.` - cinco pseudo-palavras
   com pontos soltos, que a legenda mostrava uma a uma. Ilegivel.
2. PONTUACAO ORFA. Token cujo texto e so `.` ou `,`, sem palavra nenhuma.
3. DURACAO ZERO. Palavra com `end == start` (medido: 15 em 1319 no video de teste).
   No karaoke isso vira `\\k0` e a palavra nunca acende; alem disso o timestamp fica
   fora de ordem em relacao a vizinha.
4. REPETICAO ALUCINADA. Whisper entra em loop em trecho de silencio ou musica e repete a
   mesma palavra dezenas de vezes.

Roda DENTRO de cada transcriber (`build_result*`), nao no pipeline: assim o
`transcription.json` salvo em cache ja nasce normalizado e existe uma unica versao da
verdade. Como a normalizacao junta e descarta tokens, ela renumera os `word_id` no fim -
por isso precisa acontecer ANTES de qualquer coisa que guarde word_id (selecao, manifesto).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from clipador.transcribe.models import Segment, TranscriptionResult, Word, renumber_words

logger = logging.getLogger(__name__)

_PUNCTUATION_ONLY = re.compile(r"^[^\w]+$", re.UNICODE)
# Uma unica letra maiuscula, com ponto opcional antes e/ou depois: o formato em que o ASR
# devolve cada letra de uma sigla soletrada.
_ACRONYM_LETTER = re.compile(r"^\.?([A-ZÀ-ÖØ-Þ])\.?$")
_TRAILING_KEPT = ",;:!?"

# Um run precisa de pelo menos 3 letras E de pelo menos 2 tokens pontuados pra ser tratado
# como sigla. Sem esses dois pisos, "a", "e", "o" (palavras de verdade em PT-BR) seriam
# grudadas em siglas inexistentes.
_MIN_ACRONYM_LETTERS = 3
_MIN_ACRONYM_DOTS = 2


@dataclass(frozen=True)
class NormalizationRules:
    # 80ms e o piso abaixo do qual o destaque de uma palavra nao chega a ser percebido.
    min_word_seconds: float = 0.08
    # Ate 3 repeticoes seguidas da mesma palavra sao fala real ("nao, nao, nao"); acima
    # disso e loop do decoder.
    max_repetition_run: int = 3
    # Teto por palavra ao redistribuir um trecho que o alinhador colapsou num instante so.
    max_spread_word_seconds: float = 0.5
    merge_acronyms: bool = True
    attach_orphan_punctuation: bool = True


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip(".,;:!?")


def _drop_empty(words: Sequence[Word]) -> list[Word]:
    return [word for word in words if word.text.strip()]


def _attach_orphan_punctuation(words: Sequence[Word]) -> list[Word]:
    """Cola token que e so pontuacao na palavra anterior. Sem palavra anterior, descarta:
    uma legenda que abre com um `.` solto nao ajuda ninguem."""
    result: list[Word] = []
    for word in words:
        if _PUNCTUATION_ONLY.match(word.text.strip()):
            if result:
                previous = result[-1]
                result[-1] = Word(
                    id=previous.id,
                    text=previous.text + word.text.strip(),
                    start=previous.start,
                    end=max(previous.end, word.end),
                    speaker=previous.speaker,
                )
            continue
        result.append(word)
    return result


def _acronym_run_length(words: Sequence[Word], start: int) -> int:
    letters = 0
    dotted = 0
    index = start
    while index < len(words):
        match = _ACRONYM_LETTER.match(words[index].text.strip())
        if match is None:
            break
        letters += 1
        if "." in words[index].text:
            dotted += 1
        index += 1
    if letters < _MIN_ACRONYM_LETTERS or dotted < _MIN_ACRONYM_DOTS:
        return 0
    return letters


def _merge_acronyms(words: Sequence[Word]) -> list[Word]:
    """Junta a sigla soletrada numa palavra so, sem os pontos internos.

    O ponto final do ultimo token e descartado: nele nao da pra separar "ponto da sigla"
    de "ponto que fecha a frase". Pontuacao terminal inequivoca (`?`, `!`, `,`, `;`, `:`)
    e preservada.
    """
    result: list[Word] = []
    index = 0
    while index < len(words):
        run = _acronym_run_length(words, index)
        if run == 0:
            result.append(words[index])
            index += 1
            continue
        chunk = words[index : index + run]
        letters = "".join(
            _ACRONYM_LETTER.match(word.text.strip()).group(1)  # type: ignore[union-attr]
            for word in chunk
        )
        tail = chunk[-1].text.strip()[-1]
        suffix = tail if tail in _TRAILING_KEPT else ""
        logger.debug("Sigla remontada: %r -> %r", [w.text for w in chunk], letters + suffix)
        result.append(
            Word(
                id=chunk[0].id,
                text=letters + suffix,
                start=chunk[0].start,
                end=chunk[-1].end,
                speaker=chunk[0].speaker,
            )
        )
        index += run
    return result


def _collapse_repetitions(words: Sequence[Word], max_run: int) -> list[Word]:
    result: list[Word] = []
    run_key: str | None = None
    run_length = 0
    for word in words:
        key = _fold(word.text)
        if key and key == run_key:
            run_length += 1
        else:
            run_key = key
            run_length = 1
        if run_length > max_run:
            continue
        result.append(word)
    return result


def _degenerate(word: Word) -> bool:
    return word.end <= word.start


def _spread_degenerate_runs(
    words: Sequence[Word], max_word_seconds: float
) -> list[Word]:
    """Redistribui trechos em que o alinhador colapsou VARIAS palavras no mesmo instante.

    Acontece quando o alinhamento CTC nao acha fonema para uma sequencia inteira: no
    video de teste, cinco palavras seguidas voltaram todas com `start == end == 151.72`.
    Elas ficariam com `\\k0` no karaoke, ou seja, o destaque pularia a frase toda.

    So vale para run de 2+ palavras: uma palavra isolada sem timestamp (numero, simbolo)
    e resolvida pela duracao minima, e espalha-la pelo silencio seguinte a deixaria na
    tela por tempo que ela nao foi falada.
    """
    result = list(words)
    index = 0
    while index < len(result):
        if not _degenerate(result[index]):
            index += 1
            continue

        start = result[index].start
        degenerate_count = 0
        end_of_run = index - 1
        # O cluster vai ate a primeira palavra que comeca DEPOIS do instante colapsado.
        # A ultima palavra do cluster costuma ter duracao propria (no video de teste,
        # seis palavras em 151.72 seguidas de "capacidade" 151.72->152.48): e o fim dela
        # que define o espaco disponivel, entao ela entra na redistribuicao.
        while end_of_run + 1 < len(result) and result[end_of_run + 1].start <= start:
            end_of_run += 1
            degenerate_count += int(_degenerate(result[end_of_run]))
        length = end_of_run - index + 1
        if degenerate_count < 2:
            index = end_of_run + 1
            continue

        limit = (
            result[end_of_run + 1].start
            if end_of_run + 1 < len(result)
            else max(result[end_of_run].end, start + length * max_word_seconds)
        )
        window = min(limit - start, length * max_word_seconds)
        if window > 0:
            step = window / length
            for offset in range(length):
                word = result[index + offset]
                result[index + offset] = Word(
                    id=word.id,
                    text=word.text,
                    start=start + step * offset,
                    end=start + step * (offset + 1),
                    speaker=word.speaker,
                )
            logger.debug(
                "Alinhamento colapsado: %d palavra(s) redistribuida(s) em %.2fs a partir de %.2fs",
                length,
                window,
                start,
            )
        index = end_of_run + 1
    return result


def _fix_timings(words: Sequence[Word], min_seconds: float) -> list[Word]:
    """Garante duracao minima sem invadir a palavra seguinte, e ordem nao decrescente.

    O karaoke soma as duracoes em sequencia a partir do inicio da cue; um `end` maior que
    o `start` do vizinho faria o acumulado dessincronizar do audio a partir dali.
    """
    result: list[Word] = []
    for index, word in enumerate(words):
        start = max(0.0, word.start)
        end = max(word.end, start)
        if end - start < min_seconds:
            end = start + min_seconds
        if index + 1 < len(words):
            end = min(end, max(start, words[index + 1].start))
        result.append(Word(id=word.id, text=word.text.strip(), start=start, end=end, speaker=word.speaker))
    return result


def clean_words(words: Sequence[Word], rules: NormalizationRules) -> list[Word]:
    """Limpeza de TEXTO (sigla, pontuacao orfa, repeticao). Nao mexe em tempo: o ajuste
    de tempo precisa enxergar a palavra seguinte, que pode estar no proximo segmento."""
    result = _drop_empty(words)
    if rules.attach_orphan_punctuation:
        result = _attach_orphan_punctuation(result)
    if rules.merge_acronyms:
        result = _merge_acronyms(result)
    return _collapse_repetitions(result, rules.max_repetition_run)


def normalize_words(words: Sequence[Word], rules: NormalizationRules) -> list[Word]:
    """Limpeza de texto + ajuste de tempo de uma sequencia contigua de palavras."""
    cleaned = _spread_degenerate_runs(
        clean_words(words, rules), rules.max_spread_word_seconds
    )
    return _fix_timings(cleaned, rules.min_word_seconds)


def normalize_transcription(
    result: TranscriptionResult, rules: NormalizationRules = NormalizationRules()
) -> TranscriptionResult:
    """Devolve uma transcricao nova, normalizada e com `word_id` renumerados."""
    cleaned = [clean_words(segment.words, rules) for segment in result.segments]

    # O ajuste de tempo roda sobre a lista PLANA, atravessando a fronteira de segmento.
    # Rodando por segmento, a duracao minima da ultima palavra de um segmento era
    # esticada sem enxergar a primeira palavra do seguinte, e a normalizacao criava
    # sobreposicao onde a transcricao crua nao tinha (2 casos no video de teste).
    flat = _fix_timings(
        _spread_degenerate_runs(
            [word for group in cleaned for word in group], rules.max_spread_word_seconds
        ),
        rules.min_word_seconds,
    )

    segments: list[Segment] = []
    cursor = 0
    for segment, group in zip(result.segments, cleaned, strict=True):
        words = flat[cursor : cursor + len(group)]
        cursor += len(group)
        if not words:
            continue
        segments.append(
            Segment(
                id=segment.id,
                start=words[0].start,
                end=words[-1].end,
                # Reescrito a partir das palavras: depois de juntar sigla e cortar
                # repeticao, o `text` original deixaria de bater com o que vai pra tela e
                # com o que o LLM de selecao ve.
                text=" ".join(word.text for word in words),
                words=words,
                speaker=segment.speaker,
            )
        )

    dropped = len(result.words) - sum(len(segment.words) for segment in segments)
    if dropped:
        logger.info("Normalizacao da transcricao: %d token(s) removido(s)/fundido(s)", dropped)

    renumber_words(segments)
    return TranscriptionResult(
        segments=segments,
        language=result.language,
        duration=result.duration,
        audio_path=result.audio_path,
    )
