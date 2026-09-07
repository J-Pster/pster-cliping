"""Baixa as fontes embarcadas da legenda para `engine/assets/fonts/`.

As quatro fontes sao versionadas no repo (sao ~800KB no total e mudar de fonte muda o
produto), entao no uso normal este script nao precisa rodar. Ele existe para tornar a
origem de cada arquivo auditavel e para reconstruir o diretorio se alguem apagar.

Todas sao licenciadas sob a SIL Open Font License 1.1, que permite uso comercial,
redistribuicao e embutir no produto. Ver `assets/fonts/README.md`.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

SOURCES: dict[str, str] = {
    "Montserrat-ExtraBold.ttf": (
        "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/"
        "Montserrat-ExtraBold.ttf"
    ),
    "Anton-Regular.ttf": (
        "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf"
    ),
    "ArchivoBlack-Regular.ttf": (
        "https://github.com/google/fonts/raw/main/ofl/archivoblack/ArchivoBlack-Regular.ttf"
    ),
    "BebasNeue-Regular.ttf": (
        "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf"
    ),
}


def main() -> int:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for file_name, url in SOURCES.items():
        target = FONTS_DIR / file_name
        print(f"baixando {file_name} de {url}")
        with urllib.request.urlopen(url) as response:  # noqa: S310 - URLs fixas acima
            data = response.read()
        # Um .ttf comeca com a tag de versao `\x00\x01\x00\x00` (TrueType) ou "true"/"OTTO".
        # Sem essa checagem, uma pagina de erro HTTP viraria um arquivo .ttf invalido em
        # disco e o libass so falharia muito depois, na hora do burn-in.
        if data[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf"):
            print(f"ERRO: {url} nao devolveu um TrueType valido", file=sys.stderr)
            return 1
        target.write_bytes(data)
        print(f"  -> {target} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
