"""Normalizacao da transcricao crua: os quatro defeitos de ASR que chegavam na legenda."""

from __future__ import annotations

import pytest

from clipador.transcribe.models import Segment, TranscriptionResult, Word
from clipador.transcribe.normalize import (
    NormalizationRules,
    normalize_transcription,
    normalize_words,
)


def _words(*pairs: tuple[str, float, float]) -> list[Word]:
    return [Word(id=i, text=t, start=s, end=e) for i, (t, s, e) in enumerate(pairs)]


def _texts(words) -> list[str]:
    return [w.text for w in words]


# --------------------------------------------------------------------------- sigla


def test_remonta_sigla_soletrada_pelo_asr():
    """Medido no video de teste: "GAECO" volta do Whisper como cinco pseudo-palavras com
    pontos soltos, e a legenda mostrava uma por vez."""
    words = _words(("G", 0.0, 0.2), (".A", 0.2, 0.4), (".E", 0.4, 0.6), (".C", 0.6, 0.8), (".O.", 0.8, 1.0))

    assert _texts(normalize_words(words, NormalizationRules())) == ["GAECO"]


def test_sigla_remontada_cobre_o_intervalo_inteiro_do_run():
    words = _words(("G", 0.0, 0.2), (".A", 0.2, 0.4), (".E", 0.4, 0.9))

    (merged,) = normalize_words(words, NormalizationRules())

    assert (merged.start, merged.end) == (0.0, 0.9)


def test_nao_junta_palavras_de_uma_letra_que_sao_palavras_de_verdade():
    """"a", "e", "o" sao palavras em PT-BR: sem o piso de tokens pontuados elas virariam
    uma sigla inexistente."""
    words = _words(("A", 0.0, 0.2), ("e", 0.2, 0.4), ("o", 0.4, 0.6), ("povo", 0.6, 1.0))

    assert _texts(normalize_words(words, NormalizationRules())) == ["A", "e", "o", "povo"]


def test_merge_de_sigla_pode_ser_desligado():
    words = _words(("G", 0.0, 0.2), (".A", 0.2, 0.4), (".E", 0.4, 0.6))

    assert len(normalize_words(words, NormalizationRules(merge_acronyms=False))) == 3


# --------------------------------------------------------------------------- pontuacao


def test_pontuacao_orfa_cola_na_palavra_anterior():
    words = _words(("tribunais", 0.0, 0.5), (".", 0.5, 0.6), ("Ponto", 0.6, 1.0))

    assert _texts(normalize_words(words, NormalizationRules())) == ["tribunais.", "Ponto"]


def test_pontuacao_orfa_no_inicio_e_descartada():
    words = _words((".", 0.0, 0.1), ("Ponto", 0.1, 0.5))

    assert _texts(normalize_words(words, NormalizationRules())) == ["Ponto"]


def test_token_vazio_e_descartado():
    words = _words(("   ", 0.0, 0.1), ("ok", 0.1, 0.5))

    assert _texts(normalize_words(words, NormalizationRules())) == ["ok"]


# --------------------------------------------------------------------------- duracao


def test_palavra_de_duracao_zero_ganha_o_minimo():
    """Com `end == start` o karaoke gera `\\k0` e a palavra nunca acende."""
    words = _words(("meta", 0.0, 0.5), ("2026", 0.5, 0.5), ("agora", 1.2, 2.0))

    result = normalize_words(words, NormalizationRules(min_word_seconds=0.08))

    assert result[1].end == pytest.approx(0.58)


def test_duracao_minima_nao_invade_a_palavra_seguinte():
    """O karaoke soma as duracoes em sequencia: `end` alem do `start` do vizinho
    dessincroniza tudo dali pra frente."""
    words = _words(("a", 0.0, 0.0), ("b", 0.02, 0.5))

    result = normalize_words(words, NormalizationRules(min_word_seconds=0.08))

    assert result[0].end <= result[1].start


def test_end_menor_que_start_e_corrigido():
    words = _words(("torto", 1.0, 0.5), ("depois", 2.0, 2.5))

    result = normalize_words(words, NormalizationRules())

    assert result[0].end >= result[0].start


def test_redistribui_trecho_que_o_alinhador_colapsou_num_instante_so():
    """Forma medida no video de teste: seis palavras em 151.72 seguidas de uma com
    duracao propria. Sem redistribuir, o karaoke pula a frase inteira."""
    words = _words(
        ("temos", 151.26, 151.52),
        ("de", 151.72, 151.72),
        ("revertir", 151.72, 151.72),
        ("o", 151.72, 151.72),
        ("capacidade", 151.72, 152.48),
        ("institucional", 152.48, 153.82),
    )

    result = normalize_words(words, NormalizationRules())

    colapsadas = result[1:5]
    assert all(w.end > w.start for w in colapsadas)
    assert colapsadas[0].start == pytest.approx(151.72)
    assert colapsadas[-1].end == pytest.approx(152.48)
    assert result[5].start == pytest.approx(152.48)  # a palavra seguinte nao se move


def test_palavra_isolada_sem_timestamp_nao_e_espalhada_pelo_silencio():
    """Numero e simbolo voltam do CTC sem alinhamento; espalhar um deles pelo silencio
    seguinte o deixaria na tela por tempo que nao foi falado. A duracao minima basta."""
    words = _words(("meta", 0.0, 0.5), ("2026", 0.5, 0.5), ("agora", 2.0, 2.4))

    result = normalize_words(words, NormalizationRules(min_word_seconds=0.08))

    assert result[1].end == pytest.approx(0.58)


def test_redistribuicao_respeita_o_teto_por_palavra():
    words = _words(("a", 0.0, 0.0), ("b", 0.0, 0.0), ("c", 0.0, 30.0))

    result = normalize_words(words, NormalizationRules(max_spread_word_seconds=0.5))

    assert all(w.end - w.start <= 0.5 + 1e-9 for w in result)


# --------------------------------------------------------------------------- repeticao


def test_corta_loop_de_repeticao_do_decoder():
    words = _words(*[("nao", i * 0.3, i * 0.3 + 0.25) for i in range(10)])

    result = normalize_words(words, NormalizationRules(max_repetition_run=3))

    assert len(result) == 3


def test_repeticao_dentro_do_limite_e_fala_de_verdade():
    words = _words(("nao", 0.0, 0.3), ("nao", 0.4, 0.7), ("nao", 0.8, 1.1))

    assert len(normalize_words(words, NormalizationRules(max_repetition_run=3))) == 3


def test_repeticao_e_comparada_sem_acento_e_sem_pontuacao():
    words = _words(("Não,", 0.0, 0.3), ("nao", 0.4, 0.7), ("NÃO.", 0.8, 1.1), ("nao", 1.2, 1.5))

    assert len(normalize_words(words, NormalizationRules(max_repetition_run=2))) == 2


# --------------------------------------------------------------------------- transcricao


def _transcription() -> TranscriptionResult:
    return TranscriptionResult(
        segments=[
            Segment(
                id=0,
                start=0.0,
                end=1.0,
                text=" G .A .E .C .O. atua",
                words=_words(
                    ("G", 0.0, 0.2), (".A", 0.2, 0.4), (".E", 0.4, 0.6),
                    (".C", 0.6, 0.8), (".O.", 0.8, 1.0), ("atua", 1.0, 1.4),
                ),
            ),
            Segment(id=1, start=2.0, end=2.5, text="hoje", words=_words(("hoje", 2.0, 2.5))),
        ],
        language="pt",
        duration=3.0,
    )


def test_normalizacao_renumera_os_word_ids_apos_fundir_tokens():
    """Os `word_id` sao a referencia estavel da selecao e do manifesto: fundir tokens sem
    renumerar deixaria buracos na sequencia."""
    result = normalize_transcription(_transcription())

    assert [w.id for w in result.words] == [0, 1, 2]
    assert [w.text for w in result.words] == ["GAECO", "atua", "hoje"]


def test_texto_do_segmento_e_reescrito_a_partir_das_palavras():
    """Depois de juntar sigla e cortar repeticao, o `text` original deixaria de bater com
    o que vai pra tela e com o que o LLM de selecao ve."""
    result = normalize_transcription(_transcription())

    assert result.segments[0].text == "GAECO atua"


def test_limites_do_segmento_acompanham_as_palavras():
    result = normalize_transcription(_transcription())

    assert result.segments[0].start == 0.0
    assert result.segments[0].end == pytest.approx(1.4)


def test_segmento_que_fica_sem_palavra_e_descartado():
    source = TranscriptionResult(
        segments=[
            Segment(id=0, start=0.0, end=0.2, text=".", words=_words((".", 0.0, 0.2))),
            Segment(id=1, start=1.0, end=1.5, text="ok", words=_words(("ok", 1.0, 1.5))),
        ]
    )

    result = normalize_transcription(source)

    assert len(result.segments) == 1
    assert result.segments[0].text == "ok"


def test_metadados_da_transcricao_sao_preservados():
    result = normalize_transcription(_transcription())

    assert result.language == "pt"
    assert result.duration == 3.0
