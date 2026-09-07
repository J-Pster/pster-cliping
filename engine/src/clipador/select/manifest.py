"""Persistencia do que ja foi selecionado por video, pra sustentar "gerar mais" sem
repetir contexto e sem reprocessar o que ja foi exportado.

Guarda, por formato (curto/longo NAO compartilham a lista - o mesmo assunto pode virar
um clipe curto E um longo, so nao pode repetir duas vezes NO MESMO formato):
- os intervalos de word_id ja usados (pra excluir da proxima selecao);
- o proximo indice de `clip_id` (pra numeracao continuar entre rodadas, sem colidir
  com pasta ja exportada).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass
class SelectionManifest:
    used_ranges: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    next_index: dict[str, int] = field(default_factory=dict)

    def ranges_for(self, clip_format: str) -> list[tuple[int, int]]:
        return list(self.used_ranges.get(clip_format, []))

    def allocate_index(self, clip_format: str) -> int:
        """Consome e devolve o proximo indice de clip_id do formato, pra numeracao de
        pasta ficar estavel mesmo se o clipe depois falhar numa etapa. NAO marca o
        trecho como usado: isso e `mark_used`, chamado so apos exportar com sucesso."""
        index = self.next_index.get(clip_format, 0)
        self.next_index[clip_format] = index + 1
        return index

    def mark_used(self, clip_format: str, start_word_id: int, end_word_id: int) -> None:
        """Registra o trecho como usado (exclui de selecoes futuras). Chamar SO depois
        do clipe ser exportado com sucesso: marcar antes faria um erro transitorio numa
        etapa (ex.: o LLM de metadados recusando o schema) queimar o trecho pra sempre
        sem ele nunca ter virado clipe de verdade."""
        self.used_ranges.setdefault(clip_format, []).append((start_word_id, end_word_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "used_ranges": {
                fmt: [list(pair) for pair in ranges] for fmt, ranges in self.used_ranges.items()
            },
            "next_index": dict(self.next_index),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SelectionManifest:
        used_ranges = {
            fmt: [(int(pair[0]), int(pair[1])) for pair in ranges]
            for fmt, ranges in data.get("used_ranges", {}).items()
        }
        next_index = {fmt: int(value) for fmt, value in data.get("next_index", {}).items()}
        return cls(used_ranges=used_ranges, next_index=next_index)


def load_manifest(path: str | Path) -> SelectionManifest:
    target = Path(path)
    if not target.is_file():
        return SelectionManifest()
    return SelectionManifest.from_dict(json.loads(target.read_text(encoding="utf-8")))


def save_manifest(manifest: SelectionManifest, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target
