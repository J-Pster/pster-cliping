"""Etapa 7: geração de título, descrição e hashtags via LLM, com contexto da base de conhecimento."""

from clipador.metadata.generator import generate_metadata
from clipador.metadata.models import ClipMetadata

__all__ = ["ClipMetadata", "generate_metadata"]

