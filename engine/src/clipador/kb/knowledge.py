"""Base de conhecimento em duas camadas: dossie core (injetado no prompt) + arquivos por topico."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

CORE_DIRNAME = "core"
TOPICS_DIRNAME = "topics"


def _normalize(text: str) -> str:
    """Casefold + remocao de acentos, para busca tolerante em PT-BR."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _title_of(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


@dataclass
class KnowledgeDocument:
    name: str
    title: str
    content: str

    @classmethod
    def from_path(cls, path: Path) -> KnowledgeDocument:
        content = path.read_text(encoding="utf-8").strip()
        return cls(name=path.stem, title=_title_of(content, path.stem), content=content)


@dataclass
class TopicMatch:
    document: str
    heading: str
    excerpt: str
    score: int


@dataclass
class KnowledgeBase:
    movement: str
    core: list[KnowledgeDocument] = field(default_factory=list)
    topics_dir: Path | None = None

    def dossier(self) -> str:
        """Camada 1: concatenacao estavel do core, pronta para injecao com prompt caching."""
        if not self.core:
            return ""
        blocks = [f"# Dossie: {self.movement}"]
        blocks.extend(f"## {doc.title}\n\n{doc.content}" for doc in self.core)
        return "\n\n".join(blocks)


def load_knowledge_base(root: str | Path, movement: str | None = None) -> KnowledgeBase:
    root_path = Path(root)
    core_dir = root_path / CORE_DIRNAME
    documents = (
        [KnowledgeDocument.from_path(p) for p in sorted(core_dir.glob("*.md"))]
        if core_dir.is_dir()
        else []
    )
    topics_dir = root_path / TOPICS_DIRNAME
    return KnowledgeBase(
        movement=movement or root_path.name,
        core=documents,
        topics_dir=topics_dir if topics_dir.is_dir() else None,
    )


def search_topics(
    kb: KnowledgeBase,
    query: str,
    max_results: int = 5,
    context_lines: int = 2,
) -> list[TopicMatch]:
    """Camada 2: busca por substring nos arquivos de topico (sem indice, editavel a mao)."""
    terms = [_normalize(term) for term in query.split() if term.strip()]
    if not terms or kb.topics_dir is None:
        return []

    matches: list[TopicMatch] = []
    for path in sorted(kb.topics_dir.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        headings = _heading_per_line(lines)
        hits_by_heading: dict[str, list[int]] = {}
        for index, line in enumerate(lines):
            normalized = _normalize(line)
            if all(term in normalized for term in terms):
                hits_by_heading.setdefault(headings[index], []).append(index)

        for heading, indexes in hits_by_heading.items():
            matches.append(
                TopicMatch(
                    document=path.stem,
                    heading=heading,
                    excerpt=_excerpt(lines, indexes, context_lines),
                    score=len(indexes),
                )
            )

    matches.sort(key=lambda m: (-m.score, m.document, m.heading))
    return matches[:max_results]


def _heading_per_line(lines: list[str]) -> list[str]:
    headings: list[str] = []
    current = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            current = stripped.lstrip("#").strip()
        headings.append(current)
    return headings


def _excerpt(lines: list[str], indexes: list[int], context_lines: int) -> str:
    wanted: set[int] = set()
    for index in indexes:
        start = max(0, index - context_lines)
        end = min(len(lines), index + context_lines + 1)
        wanted.update(range(start, end))

    ordered = sorted(wanted)
    chunks: list[list[str]] = []
    previous: int | None = None
    for index in ordered:
        if previous is None or index != previous + 1:
            chunks.append([])
        chunks[-1].append(lines[index])
        previous = index
    return "\n\n".join("\n".join(chunk).strip() for chunk in chunks).strip()
