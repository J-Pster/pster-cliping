"""Ajuste de corte para a pausa de silencio mais proxima, trabalhando sempre em word_id."""

from __future__ import annotations

from clipador.transcribe.models import TranscriptionResult, Word

DEFAULT_SILENCE_GAP = 0.3


def silence_boundaries(
    words: list[Word], threshold: float = DEFAULT_SILENCE_GAP
) -> tuple[list[int], list[int]]:
    """Indices de palavras que iniciam e que encerram um bloco de fala continuo."""
    if not words:
        return [], []

    starts = [0]
    ends = [len(words) - 1]
    for index in range(1, len(words)):
        if words[index].start - words[index - 1].end >= threshold:
            starts.append(index)
            ends.append(index - 1)

    return sorted(set(starts)), sorted(set(ends))


def snap_to_silence(
    transcription: TranscriptionResult,
    start_word_id: int,
    end_word_id: int,
    threshold: float = DEFAULT_SILENCE_GAP,
) -> tuple[int, int]:
    """Move inicio/fim do corte para a pausa mais proxima, sem sair do range da transcricao."""
    words = transcription.words
    if not words:
        raise ValueError("transcricao sem palavras: nao ha corte possivel")

    index_by_id = {word.id: index for index, word in enumerate(words)}
    if start_word_id not in index_by_id or end_word_id not in index_by_id:
        raise KeyError(f"word_id fora da transcricao: {start_word_id}-{end_word_id}")

    start_index = index_by_id[start_word_id]
    end_index = index_by_id[end_word_id]
    if start_index > end_index:
        raise ValueError("start_word_id posterior a end_word_id")

    starts, ends = silence_boundaries(words, threshold)
    snapped_start = _nearest(starts, start_index)
    snapped_end = _nearest(ends, end_index)
    if snapped_start > snapped_end:
        snapped_start, snapped_end = start_index, end_index

    return words[snapped_start].id, words[snapped_end].id


def _nearest(candidates: list[int], target: int) -> int:
    # Empate de distancia resolve sempre para o indice anterior, para o corte ser deterministico.
    return min(candidates, key=lambda index: (abs(index - target), index > target))


def expand_to_min_duration(
    transcription: TranscriptionResult,
    start_word_id: int,
    end_word_id: int,
    min_seconds: float,
    max_seconds: float,
    threshold: float = DEFAULT_SILENCE_GAP,
) -> tuple[int, int] | None:
    """Estende `[start_word_id, end_word_id]` pra tras e pra frente, um bloco de fala
    continua por vez (nos boundaries de `silence_boundaries`), ate atingir `min_seconds`
    sem estourar `max_seconds`. Alterna a direcao de crescimento a cada passo pra puxar
    contexto dos dois lados quando os dois tem bloco disponivel, em vez de so um -
    reparo determinístico pro caso do LLM propor um trecho curto demais pro formato
    (ex.: rotular 90s como long_16x9, que exige 5min).

    Devolve `None` quando nao da pra atingir `min_seconds` sem passar de `max_seconds`
    (ex.: perto da borda da transcricao, ou os blocos vizinhos sao grandes demais) - o
    chamador deve descartar o candidato nesse caso, nunca exportar fora da janela."""
    words = transcription.words
    if not words:
        return None

    index_by_id = {word.id: index for index, word in enumerate(words)}
    if start_word_id not in index_by_id or end_word_id not in index_by_id:
        return None

    start_index = index_by_id[start_word_id]
    end_index = index_by_id[end_word_id]
    if start_index > end_index:
        return None

    starts, ends = silence_boundaries(words, threshold)
    blocks = list(zip(starts, ends))
    left = min(range(len(blocks)), key=lambda i: abs(blocks[i][0] - start_index))
    right = min(range(len(blocks)), key=lambda i: abs(blocks[i][1] - end_index))
    if left > right:
        left, right = right, left

    def block_span_seconds(left_pos: int, right_pos: int) -> float:
        return words[blocks[right_pos][1]].end - words[blocks[left_pos][0]].start

    # O bloco de fala continua que ja contem o candidato pode, sozinho, ja passar do
    # teto (ex.: transcricao sem pausa nenhuma por perto) - nesse caso nao ha reparo
    # possivel (so cresce, nunca encolhe), desiste antes de entrar no loop de expansao.
    if block_span_seconds(left, right) > max_seconds:
        return None

    grow_forward = True
    while block_span_seconds(left, right) < min_seconds:
        expanded = False
        if grow_forward and right + 1 < len(blocks):
            right += 1
            expanded = True
        elif not grow_forward and left > 0:
            left -= 1
            expanded = True
        elif right + 1 < len(blocks):
            right += 1
            expanded = True
        elif left > 0:
            left -= 1
            expanded = True
        if not expanded:
            return None
        grow_forward = not grow_forward
        if block_span_seconds(left, right) > max_seconds:
            return None

    return words[blocks[left][0]].id, words[blocks[right][1]].id
