"""Acceso a SQLite (stdlib, sin ORM)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .config import get_settings
from .normalize import is_affix, is_proper

SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
    id           INTEGER PRIMARY KEY,
    word         TEXT    NOT NULL UNIQUE,
    word_norm    TEXT    NOT NULL,
    first_letter TEXT    NOT NULL,
    letter_count INTEGER NOT NULL,
    is_phrase    INTEGER NOT NULL DEFAULT 0,
    is_affix     INTEGER NOT NULL DEFAULT 0,  -- prefijo ('supra-') o sufijo ('-algia')
    is_proper    INTEGER NOT NULL DEFAULT 0,  -- nombre propio ('Madrid'), no sigla
    zipf         REAL    NOT NULL DEFAULT 0,  -- frecuencia de uso; 0 = sin datos
    freq_tier    TEXT    NOT NULL DEFAULT 'unknown',
    freq_source  TEXT                         -- 'wordfreq' | 'opensubtitles'
);
CREATE INDEX IF NOT EXISTS idx_words_first_letter ON words(first_letter);
CREATE INDEX IF NOT EXISTS idx_words_letter_count ON words(letter_count);
CREATE INDEX IF NOT EXISTS idx_words_word_norm    ON words(word_norm);
CREATE INDEX IF NOT EXISTS idx_words_zipf         ON words(zipf);

CREATE TABLE IF NOT EXISTS definitions (
    word       TEXT PRIMARY KEY,
    word_norm  TEXT NOT NULL,
    source     TEXT NOT NULL,
    data       TEXT NOT NULL,        -- JSON con las acepciones
    fetched_at TEXT NOT NULL         -- ISO-8601 UTC
);
CREATE INDEX IF NOT EXISTS idx_definitions_word_norm ON definitions(word_norm);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def db_path() -> Path:
    return Path(get_settings().database_path)


def connect(read_only: bool = False) -> sqlite3.Connection:
    path = db_path()
    if read_only:
        uri = f"file:{path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_connection(read_only: bool = False) -> Iterator[sqlite3.Connection]:
    conn = connect(read_only=read_only)
    try:
        yield conn
        if not read_only:
            conn.commit()
    finally:
        conn.close()


def migrate(conn: sqlite3.Connection) -> None:
    """Pone al día una base ya existente. Idempotente y sin perder datos.

    Evita tener que reconstruir el índice entero (que implica descargar el
    lemario) cada vez que el esquema gana una columna derivada.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(words)")}
    if not columns:
        return  # base recién creada: SCHEMA ya trae todo

    if "is_affix" not in columns:
        conn.execute("ALTER TABLE words ADD COLUMN is_affix INTEGER NOT NULL DEFAULT 0")
        # El relleno usa la misma función que el indexado: una sola fuente de verdad.
        rows = conn.execute("SELECT id, word FROM words").fetchall()
        conn.executemany(
            "UPDATE words SET is_affix = 1 WHERE id = ?",
            [(row["id"],) for row in rows if is_affix(row["word"])],
        )

    if "is_proper" not in columns:
        conn.execute("ALTER TABLE words ADD COLUMN is_proper INTEGER NOT NULL DEFAULT 0")
        rows = conn.execute("SELECT id, word FROM words").fetchall()
        conn.executemany(
            "UPDATE words SET is_proper = 1 WHERE id = ?",
            [(row["id"],) for row in rows if is_proper(row["word"])],
        )

    if "zipf" not in columns:
        # Estas no se pueden rellenar aquí: los datos son externos y los trae
        # scripts/enrich_frequency.py. Hasta entonces, todo queda en 'unknown'.
        conn.execute("ALTER TABLE words ADD COLUMN zipf REAL NOT NULL DEFAULT 0")
        conn.execute(
            "ALTER TABLE words ADD COLUMN freq_tier TEXT NOT NULL DEFAULT 'unknown'"
        )
        conn.execute("ALTER TABLE words ADD COLUMN freq_source TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_words_zipf ON words(zipf)")


def init_schema(conn: sqlite3.Connection) -> None:
    # Migrar ANTES de aplicar el esquema: SCHEMA crea índices sobre columnas
    # que en una base antigua todavía no existen (las añade migrate). En una
    # base nueva migrate no hace nada y SCHEMA lo crea todo de una vez.
    migrate(conn)
    conn.executescript(SCHEMA)


def database_exists() -> bool:
    return db_path().exists()
