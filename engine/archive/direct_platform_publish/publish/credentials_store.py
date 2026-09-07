"""Armazenamento local dos tokens de cada plataforma.

Uso pessoal, single-user, local: os tokens ficam em arquivos JSON fora do
repo (`.clipador/credentials/`, gitignored), nunca em Secrets Manager ou banco,
porque nao existe backend nem outro usuario nessa ponta do sistema ainda.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

DEFAULT_CREDENTIALS_ROOT = Path(".clipador/credentials")


def _token_path(platform: str, root: Path) -> Path:
    return root / f"{platform}.json"


def load_tokens(platform: str, root: Path = DEFAULT_CREDENTIALS_ROOT) -> dict[str, Any] | None:
    path = _token_path(platform, root)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_tokens(platform: str, data: dict[str, Any], root: Path = DEFAULT_CREDENTIALS_ROOT) -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = _token_path(platform, root)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
