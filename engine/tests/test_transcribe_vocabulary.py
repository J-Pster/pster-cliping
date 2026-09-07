"""Vocabulario de dominio extraido da KB e injetado no ASR."""

from __future__ import annotations

from clipador.kb.knowledge import KnowledgeBase, KnowledgeDocument
from clipador.transcribe.factory import TranscriberSettings, build_transcriber
from clipador.transcribe.vocabulary import Vocabulary, build_vocabulary, extract_terms


def _kb(content: str) -> KnowledgeBase:
    return KnowledgeBase(
        movement="teste",
        core=[KnowledgeDocument(name="core", title="Core", content=content)],
    )


def test_sigla_entra_mesmo_com_uma_unica_ocorrencia():
    """Sigla e onde o ASR mais erra (soletra letra a letra) e onde menos ha risco de
    falso positivo."""
    termos = extract_terms("O GAECO atuou no caso. O STF decidiu.")

    assert "GAECO" in termos
    assert "STF" in termos


def test_nome_proprio_precisa_se_repetir_para_entrar():
    termos = extract_terms("Renan falou. Renan insistiu. Aleatorio apareceu uma vez.")

    assert "Renan" in termos
    assert "Aleatorio" not in termos


def test_palavra_comum_capitalizada_no_inicio_de_frase_e_ignorada():
    termos = extract_terms("Quando chove. Quando venta. Depois passa. Depois volta.")

    assert "Quando" not in termos
    assert "Depois" not in termos


def test_sintaxe_de_markdown_nao_vira_termo():
    termos = extract_terms("# Titulo\n\n**Renan** e [Renan](https://exemplo.com/Renan)")

    assert all(termo.isalnum() or "-" in termo for termo in termos)


def test_termos_saem_ordenados_por_frequencia():
    termos = extract_terms("Alfa Alfa Alfa Beta Beta")

    assert termos.index("Alfa") < termos.index("Beta")


def test_limite_de_termos_e_respeitado():
    """`initial_prompt` tem teto de 224 tokens no proprio Whisper; passar disso e
    truncado e ainda aumenta a chance de o decoder continuar o prompt em vez de
    transcrever."""
    nomes = [f"Nome{chr(97 + i // 26)}{chr(97 + i % 26)}bcd" for i in range(100)]
    texto = " ".join(f"{nome} {nome}" for nome in nomes)

    assert len(extract_terms(texto, max_terms=10)) == 10


def test_vocabulario_vazio_nao_gera_prompt_nem_hotwords():
    vocabulario = Vocabulary()

    assert not vocabulario
    assert vocabulario.initial_prompt is None
    assert vocabulario.hotwords is None


def test_initial_prompt_e_prosa_e_cita_os_termos():
    """O Whisper foi treinado com transcricoes: um prompt que parece transcricao enviesa
    melhor que uma lista crua."""
    vocabulario = Vocabulary(terms=("GAECO", "Renan"))

    prompt = vocabulario.initial_prompt
    assert prompt is not None
    assert "portugues do Brasil" in prompt
    assert "GAECO" in prompt and "Renan" in prompt


def test_build_vocabulary_le_o_dossie_da_kb():
    vocabulario = build_vocabulary(_kb("O GAECO investigou. O GAECO concluiu."))

    assert "GAECO" in vocabulario.terms


def test_vocabulario_chega_no_transcriber_construido_pela_fabrica():
    vocabulario = Vocabulary(terms=("GAECO",))

    transcriber = build_transcriber(
        TranscriberSettings(backend="faster-whisper", device="cpu"), vocabulary=vocabulario
    )

    assert transcriber.vocabulary is vocabulario
