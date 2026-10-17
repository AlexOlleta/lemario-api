"""Descarga el lemario RAE y construye el índice SQLite.

Uso:
    python -m scripts.build_index                 # auto-detecta la última edición
    python -m scripts.build_index --file 23-8-1.txt
    python -m scripts.build_index --local ruta.txt
    python -m scripts.build_index --force         # reconstruye aunque exista

La detección automática consulta la API de GitHub del repositorio y elige el
fichero .txt con la versión más alta (p. ej. 23-8-1 > 23-8 > 23-2).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import httpx

# Permite ejecutar como script suelto (python scripts/build_index.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.database import get_connection, init_schema
from app.normalize import (
    first_letter,
    is_affix,
    is_phrase,
    is_proper,
    letter_count,
    normalize_word,
)

VERSION_RE = re.compile(r"^(\d+(?:-\d+)+)\.txt$")


def version_key(filename: str) -> tuple[int, ...] | None:
    """Convierte '23-8-1.txt' en (23, 8, 1) para poder ordenar ediciones."""
    match = VERSION_RE.match(filename)
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("-"))


def discover_latest_file(repo: str, ref: str) -> tuple[str, str]:
    """Devuelve (nombre, download_url) del fichero de versión más alta en ``ref``.

    ``ref`` es la rama, etiqueta o commit configurado (LEMARIO_LIST_BRANCH).
    """
    api = f"https://api.github.com/repos/{repo}/contents/"
    resp = httpx.get(
        api,
        params={"ref": ref},
        timeout=30,
        headers={"Accept": "application/vnd.github+json"},
    )
    resp.raise_for_status()
    candidates: list[tuple[tuple[int, ...], str, str]] = []
    for entry in resp.json():
        if entry.get("type") != "file":
            continue
        key = version_key(entry["name"])
        if key is not None:
            candidates.append((key, entry["name"], entry["download_url"]))
    if not candidates:
        raise RuntimeError(f"No se encontraron ficheros de lemario en {repo}.")
    candidates.sort()
    _, name, url = candidates[-1]
    return name, url


def raw_url(repo: str, branch: str, filename: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{filename}"


def download_text(url: str) -> str:
    resp = httpx.get(url, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def iter_words(text: str):
    seen: set[str] = set()
    for raw in text.splitlines():
        word = raw.strip()
        if not word or word in seen:
            continue
        seen.add(word)
        yield word


def build(words_text: str, list_file: str) -> int:
    settings = get_settings()
    db = Path(settings.database_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for word in iter_words(words_text):
        rows.append(
            (
                word,
                normalize_word(word),
                first_letter(word),
                letter_count(word),
                1 if is_phrase(word) else 0,
                1 if is_affix(word) else 0,
                1 if is_proper(word) else 0,
            )
        )

    with get_connection() as conn:
        init_schema(conn)
        # La caché de definiciones se conserva: es independiente.
        conn.execute("DROP TABLE IF EXISTS words")
        init_schema(conn)
        conn.executemany(
            "INSERT OR IGNORE INTO words "
            "(word, word_norm, first_letter, letter_count, is_phrase, is_affix, "
            "is_proper) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('list_file', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (list_file,),
        )
        count = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    return count


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Construye el índice SQLite de Lemario.")
    parser.add_argument(
        "--file",
        help="Nombre concreto del fichero del repo (p. ej. 23-8-1.txt). "
        "Si se omite, se auto-detecta la última edición.",
    )
    parser.add_argument(
        "--local",
        help="Ruta a un fichero local con el lemario (una palabra por línea).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reconstruye aunque la base de datos ya exista.",
    )
    args = parser.parse_args(argv)

    db = Path(settings.database_path)
    if db.exists() and not args.force:
        print(f"La base de datos ya existe: {db}. Usa --force para reconstruir.")
        return 0

    if args.local:
        local = Path(args.local)
        print(f"Leyendo lemario local: {local}")
        text = local.read_text(encoding="utf-8")
        list_file = local.name
    else:
        if args.file:
            list_file = args.file
            url = raw_url(settings.list_repo, settings.list_branch, list_file)
            print(f"Descargando fichero indicado: {list_file}")
        else:
            ref = settings.list_branch[:12]
            print(f"Detectando última edición en {settings.list_repo}@{ref}...")
            list_file, url = discover_latest_file(settings.list_repo, settings.list_branch)
            print(f"Última edición detectada: {list_file}")
        text = download_text(url)

    print("Construyendo índice (esto puede tardar la primera vez)...")
    count = build(text, list_file)
    print(f"Listo. {count} palabras indexadas en {db} (origen: {list_file}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
