"""Categoria de conteudo-fonte: a UNICA dimensao que muda os prompts de selecao de corte,
re-rank, metadados e thumbnail entre si. Cada modulo de prompt (select/selector.py,
select/rerank.py, metadata/generator.py, thumbnail/ai_thumbnail.py, thumbnail/background.py)
mantem seu proprio dict `..._BY_CATEGORY` chaveado por estas constantes - a categoria em si
nao carrega nenhum texto de prompt, so identifica qual variante usar em cada modulo.

Especificada manualmente pelo usuario a cada execucao (`--category` na CLI principal e na
de rebrand), nunca inferida do conteudo do video."""

from __future__ import annotations

POLITICS_PERSON = "politico_pessoa"
GAMING = "jogos"
BOOK_AUDIOBOOK = "livro_audiobook"

CATEGORIES = (POLITICS_PERSON, GAMING, BOOK_AUDIOBOOK)

# Usado so como default de funcoes internas chamadas direto (ex.: em teste, ou por quem
# importa select_clips/generate_metadata sem passar categoria) - a CLI nunca usa este
# default, ela exige `--category` explicito do usuario.
DEFAULT_CATEGORY = POLITICS_PERSON


def validate_category(category: str) -> str:
    """Falha alto e cedo se a categoria nao existe, em vez de deixar um prompt errado
    passar batido pro LLM (ex.: dict.get caindo silenciosamente no default)."""
    if category not in CATEGORIES:
        raise ValueError(f"Categoria desconhecida: {category!r}. Validas: {CATEGORIES}")
    return category
