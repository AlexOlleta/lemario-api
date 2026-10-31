"""Descarga el diccionario Hunspell es_ES a data/hunspell/.

Uso:
    python -m scripts.fetch_hunspell           # si no está ya descargado
    python -m scripts.fetch_hunspell --force   # vuelve a descargarlo

Es el corrector ortográfico de LibreOffice (proyecto RLA-ES), tal como lo
publica wooorm/dictionaries. Va fijado a un commit (LEMARIO_HUNSPELL_REPO y
LEMARIO_HUNSPELL_REF) para que el índice sea reproducible; para actualizarlo,
cambia el commit y descarga con --force. La copia local se queda en data/,
fuera del repositorio, junto a su licencia.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

# Permite ejecutar como script suelto (python scripts/fetch_hunspell.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings

FILES = ("index.aff", "index.dic", "license")
SOURCE_FILE = "source"


def file_url(repo: str, ref: str, name: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{ref}/dictionaries/es/{name}"


def fetch(target: Path, repo: str, ref: str) -> None:
    target.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    with httpx.Client(timeout=settings.http_timeout * 6, follow_redirects=True) as client:
        for name in FILES:
            response = client.get(file_url(repo, ref, name))
            response.raise_for_status()
            (target / name).write_bytes(response.content)
    (target / SOURCE_FILE).write_text(f"{repo}@{ref}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Descarga el diccionario Hunspell es_ES.")
    parser.add_argument("--force", action="store_true", help="Descarga aunque ya exista.")
    args = parser.parse_args(argv)

    target = Path(settings.hunspell_dir)
    if all((target / name).exists() for name in FILES) and not args.force:
        print(f"Hunspell ya está en {target}. Usa --force para volver a descargarlo.")
        return 0

    ref = settings.hunspell_ref
    print(f"Descargando Hunspell es_ES de {settings.hunspell_repo}@{ref[:12]}...")
    fetch(target, settings.hunspell_repo, ref)
    print(f"Listo en {target}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
