"""Estrutura do pacote de metadados (titulo/descricao/hashtags) gerado pelo LLM para um clipe."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClipMetadata:
    title: str
    description: str
    hashtags: list[str] = field(default_factory=list)
    format: str = ""
    kb_references: list[str] = field(default_factory=list)
    thumbnail_headline: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "hashtags": self.hashtags,
            "format": self.format,
            "kb_references": self.kb_references,
            "thumbnail_headline": self.thumbnail_headline,
        }
