"""Troca por leetspeak (letra por numero visualmente parecido) as palavras de violencia e
crime grave (matar, assassinato, bomba, estupro, sequestro etc.) em titulo, descricao e
headline da thumbnail, pra reduzir o risco de desmonetizacao ou remocao automatica pelas
plataformas (YouTube, TikTok, Instagram).

Nenhuma delas publica uma lista oficial de termos banidos - a pratica de mercado pra isso e
"algospeak": trocar um caractere por um visualmente parecido (matar -> m4t4r) pra escapar de
filtro por correspondencia EXATA de palavra, mantendo o texto legivel pra humano. So cobre
verbos/substantivos de violencia direta, nunca vocabulario politico normal do canal (golpe,
prisao, condenacao, ditadura): esses termos sao centrais ao conteudo e nao sao os que
costumam disparar moderacao automatica."""

from __future__ import annotations

import re
import unicodedata

# Radical, nao palavra inteira: cobre conjugacao/plural sem precisar listar cada forma
# (ex.: "roub" pega roubar, roubo, roubado, roubando, roubalheira). Seguro como prefixo
# solto porque nenhuma dessas raizes e prefixo de palavra comum desligada de violencia.
SIMPLE_STEMS: tuple[str, ...] = (
    "assassin",  # assassinar, assassinato, assassina, assassinaria
    "roub",  # roubar, roubo, roubado, roubalheira
    "estupr",  # estuprar, estupro, estuprador
    "suicid",  # suicidio, suicida, suicidar
    "sequestr",  # sequestro, sequestrar, sequestrado
    "tortur",  # tortura, torturar, torturado
    "chacin",  # chacina, chacinas
    "massacr",  # massacre, massacrado
    "decapit",  # decapitar, decapitado
    "atentad",  # atentado, atentados
    "genocid",  # genocidio
)

# "mat" e "bomb" NAO podem ser prefixo solto: colidem com palavra comum desligada de
# violencia (materia, matematica, matricula, Mato Grosso, bombeiro) - restritos a um
# sufixo de flexao verbal/nominal explicito. "o" bruto fica de fora do sufixo de "mat" de
# proposito: pegaria "Mato" de "Mato Grosso" (substantivo proprio, sem risco de moderacao)
# e so perderia a 1a pessoa do presente ("eu mato"), rara no tom narrativo do canal.
_MAT_SUFFIXES: tuple[str, ...] = (
    "ar", "a", "as", "amos", "ais", "am",
    "ando", "ado", "ada", "ados", "adas",
    "ei", "ou", "aste", "astes", "aram",
    "ava", "avas", "avamos", "aveis", "avam",
    "arei", "aras", "ara", "aremos", "areis", "arao",
    "aria", "arias", "ariamos", "ariam",
    "e", "es", "emos", "em",
    "asse", "asses", "assemos", "asseis", "assem",
)
_BOMB_SUFFIXES: tuple[str, ...] = (
    "a", "as",
    "ardeio", "ardeios", "ardear", "ardeando",
    "ardeado", "ardeada", "ardeados", "ardeadas",
    "ardeia", "ardeiam", "ardearam", "ardeara", "ardearia",
)
_RESTRICTED_STEMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mat", _MAT_SUFFIXES),
    ("bomb", _BOMB_SUFFIXES),
)

_LEET_MAP = str.maketrans(
    {
        "a": "4", "á": "4", "à": "4", "â": "4", "ã": "4",
        "e": "3", "é": "3", "ê": "3",
        "i": "1", "í": "1",
        "o": "0", "ó": "0", "ô": "0", "õ": "0",
    }
)

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def is_sensitive_word(word: str) -> bool:
    normalized = _strip_accents(word).lower()
    if any(normalized.startswith(stem) for stem in SIMPLE_STEMS):
        return True
    for stem, suffixes in _RESTRICTED_STEMS:
        if normalized.startswith(stem) and normalized[len(stem):] in suffixes:
            return True
    return False


def _leetspeak(word: str) -> str:
    return word.translate(_LEET_MAP)


def censor_text(text: str) -> str:
    """Troca vogal por numero so nas palavras sensiveis do texto; o resto (pontuacao,
    espacamento, capitalizacao das outras palavras) sai intacto."""
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        word = match.group(0)
        return _leetspeak(word) if is_sensitive_word(word) else word

    return _WORD_RE.sub(_replace, text)
