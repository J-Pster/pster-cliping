"""Vocabulario de dominio extraido da base de conhecimento, para condicionar o ASR.

O Whisper decide entre grafias homofonas por probabilidade de linguagem, sem saber do que
o video trata. Nome proprio e sigla sao exatamente onde ele erra mais - e sao exatamente o
que a KB do projeto ja tem escrito e revisado, arquivo por categoria, sem ninguem usar
para isso.

Duas alavancas nativas do faster-whisper recebem esse vocabulario:

- `initial_prompt`: texto injetado como contexto anterior ao audio. Enviesa a grafia do
  decoder inteiro. Tem teto duro de 224 tokens no Whisper, por isso a lista e cortada.
- `hotwords`: lista de termos com peso extra na busca. Parametro mais recente do
  faster-whisper; a existencia dele e checada na assinatura antes de passar (ver
  `clipador.transcribe.factory`), porque uma instalacao mais antiga levantaria TypeError.

A extracao e proposital e deliberadamente boba: sigla em caixa alta e palavra capitalizada
recorrente. Um NER de verdade acertaria mais, mas custaria um modelo a mais no processo
para um ganho que o corte por frequencia ja entrega quase todo.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from clipador.kb.knowledge import KnowledgeBase

# Teto conservador: `initial_prompt` acima de 224 tokens e truncado pelo proprio Whisper,
# e um prompt longo demais tambem aumenta a chance de o decoder "continuar o prompt" em
# vez de transcrever.
MAX_TERMS = 60
MIN_TERM_OCCURRENCES = 2

_ACRONYM = re.compile(r"\b[A-ZÀ-ÖØ-Þ]{2,}(?:-[A-ZÀ-ÖØ-Þ0-9]+)?\b")
_CAPITALIZED = re.compile(r"\b[A-ZÀ-ÖØ-Þ][a-zß-öø-ÿ]{2,}\b")
_MARKDOWN_NOISE = re.compile(r"[#*_`>\[\]()]|https?://\S+")

# Capitalizadas que so aparecem por comecarem frase ou por serem meses/dias. Entram no
# prompt sem agregar nada e ocupam o orcamento de tokens.
_STOPWORDS = frozenset(
    {
        "A", "As", "O", "Os", "Um", "Uma", "Ele", "Ela", "Eles", "Elas", "Esse", "Essa",
        "Este", "Esta", "Isso", "Aquele", "Aquela", "Nao", "Não", "Sim", "Mas", "Porque",
        "Quando", "Como", "Onde", "Para", "Por", "Com", "Sem", "Sobre", "Depois", "Antes",
        "Todo", "Toda", "Todos", "Todas", "Cada", "Muito", "Muita", "Ainda", "Tambem",
        "Também", "Entao", "Então", "Assim", "Agora", "Hoje", "Ontem", "Amanha", "Amanhã",
        "Janeiro", "Fevereiro", "Marco", "Março", "Abril", "Maio", "Junho", "Julho",
        "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro", "Segunda", "Terca",
        "Terça", "Quarta", "Quinta", "Sexta", "Sabado", "Sábado", "Domingo",
    }
)


@dataclass(frozen=True)
class Vocabulary:
    """Termos de dominio prontos para as duas alavancas do ASR."""

    terms: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.terms)

    @property
    def hotwords(self) -> str | None:
        """Formato aceito pelo parametro `hotwords` do faster-whisper: termos separados."""
        return ", ".join(self.terms) if self.terms else None

    @property
    def initial_prompt(self) -> str | None:
        """Frase de contexto. Escrita como prosa, nao como lista crua: o Whisper foi
        treinado com transcricoes, e um prompt que parece transcricao enviesa melhor."""
        if not self.terms:
            return None
        return (
            "Transcricao em portugues do Brasil. Nomes, siglas e termos que aparecem "
            f"neste conteudo: {', '.join(self.terms)}."
        )


def extract_terms(text: str, max_terms: int = MAX_TERMS) -> tuple[str, ...]:
    """Siglas e nomes proprios recorrentes do texto, mais frequentes primeiro."""
    clean = _MARKDOWN_NOISE.sub(" ", text)

    counts: Counter[str] = Counter()
    # Sigla entra mesmo com uma unica ocorrencia: e o caso em que o ASR mais erra
    # (soletra letra a letra) e o que menos gera falso positivo.
    counts.update(_ACRONYM.findall(clean))
    capitalized = Counter(
        token for token in _CAPITALIZED.findall(clean) if token not in _STOPWORDS
    )
    counts.update(
        {
            token: count
            for token, count in capitalized.items()
            if count >= MIN_TERM_OCCURRENCES
        }
    )

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(term for term, _ in ordered[:max_terms])


def build_vocabulary(kb: KnowledgeBase, max_terms: int = MAX_TERMS) -> Vocabulary:
    """Vocabulario do dossie core da KB da categoria em uso."""
    return Vocabulary(terms=extract_terms(kb.dossier(), max_terms))
