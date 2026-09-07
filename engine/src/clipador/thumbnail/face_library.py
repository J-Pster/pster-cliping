"""Biblioteca de fotos de referencia de rosto de figuras publicas brasileiras, usada pra
ancorar a identidade facial na geracao de thumbnail via IA quando o CONTEUDO especifico do
clipe for sobre aquela pessoa (ver `thumbnail.subject.select_thumbnail_subject`).

Cada figura vive numa pasta com 2+ fotos verificadas (`.png`/`.jpg`/`.jpeg`). Adicionar
gente nova e so: criar a pasta com fotos conferidas de verdade (rosto real, bate com a
pessoa) e acrescentar um `PoliticalFigure` novo aqui - nada mais precisa mudar, quem
consome isto (`available_figures`) so devolve quem realmente tem foto salva.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_ASSETS_ROOT = Path(__file__).resolve().parents[3] / "assets" / "thumbnail"
_FACES_ROOT = _ASSETS_ROOT / "faces"

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")


@dataclass(frozen=True)
class PoliticalFigure:
    slug: str
    display_name: str
    reference_dir: Path


def _has_photos(directory: Path) -> bool:
    return directory.is_dir() and any(p.suffix.lower() in _IMAGE_SUFFIXES for p in directory.iterdir())


# Todas as figuras vivem sob `faces/<slug>/`, mesmo padrao pra todo mundo (o apresentador
# do canal usava uma pasta `renan_santos_face/` avulsa antes desta biblioteca existir -
# migrado pra ca em 2026-09-04, mesma convencao de nome que as demais).
POLITICAL_FIGURES: tuple[PoliticalFigure, ...] = (
    PoliticalFigure("renan_santos", "Renan Santos", _FACES_ROOT / "renan_santos"),
    PoliticalFigure("jair_bolsonaro", "Jair Bolsonaro", _FACES_ROOT / "jair_bolsonaro"),
    PoliticalFigure("flavio_bolsonaro", "Flávio Bolsonaro", _FACES_ROOT / "flavio_bolsonaro"),
    PoliticalFigure("eduardo_bolsonaro", "Eduardo Bolsonaro", _FACES_ROOT / "eduardo_bolsonaro"),
    PoliticalFigure("michelle_bolsonaro", "Michelle Bolsonaro", _FACES_ROOT / "michelle_bolsonaro"),
    PoliticalFigure("arthur_do_val", "Arthur do Val", _FACES_ROOT / "arthur_do_val"),
    PoliticalFigure("ronaldo_caiado", "Ronaldo Caiado", _FACES_ROOT / "ronaldo_caiado"),
    PoliticalFigure("lula", "Luiz Inácio Lula da Silva", _FACES_ROOT / "lula"),
    PoliticalFigure("romeu_zema", "Romeu Zema", _FACES_ROOT / "romeu_zema"),
    PoliticalFigure("augusto_aras", "Augusto Aras", _FACES_ROOT / "augusto_aras"),
    PoliticalFigure("augusto_cury", "Augusto Cury", _FACES_ROOT / "augusto_cury"),
    PoliticalFigure("sergio_moro", "Sergio Moro", _FACES_ROOT / "sergio_moro"),
    PoliticalFigure("alexandre_de_moraes", "Alexandre de Moraes", _FACES_ROOT / "alexandre_de_moraes"),
    PoliticalFigure("gilmar_mendes", "Gilmar Mendes", _FACES_ROOT / "gilmar_mendes"),
)


def available_figures(figures: tuple[PoliticalFigure, ...] = POLITICAL_FIGURES) -> tuple[PoliticalFigure, ...]:
    """So devolve quem realmente tem pelo menos 1 foto salva no disco - evita a etapa de
    selecao (`thumbnail.subject`) oferecer pro LLM um nome sem nenhuma referencia pra
    anexar depois."""
    return tuple(figure for figure in figures if _has_photos(figure.reference_dir))


def find_figure(slug: str, figures: tuple[PoliticalFigure, ...] = POLITICAL_FIGURES) -> PoliticalFigure | None:
    return next((figure for figure in figures if figure.slug == slug), None)
