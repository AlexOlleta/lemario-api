"""Fixtures de pruebas.

Configura el entorno ANTES de importar la app (la configuración se cachea al
importar), construye una pequeña base de datos de prueba con casos clave en
español (ñ, tildes, locuciones) y expone un TestClient autenticado.
"""

from __future__ import annotations

import os
import tempfile

import pytest

_TMPDIR = tempfile.mkdtemp(prefix="lemario-test-")
os.environ["LEMARIO_DATABASE_PATH"] = os.path.join(_TMPDIR, "test.db")
os.environ["LEMARIO_API_KEYS"] = "testkey"
# Límites muy altos para que el rate limiting no interfiera en las pruebas.
os.environ["LEMARIO_RATE_LIMIT_DEFAULT"] = "100000/minute"
os.environ["LEMARIO_RATE_LIMIT_DEFINITIONS"] = "100000/minute"
os.environ["LEMARIO_RATE_LIMIT_EXISTS"] = "100000/minute"

from app.database import get_connection, init_schema  # noqa: E402
from app.frequency import tier_for  # noqa: E402
from app.normalize import (  # noqa: E402
    first_letter,
    is_affix,
    is_phrase,
    is_proper,
    letter_count,
    normalize_word,
)

TEST_WORDS = [
    "águila",  # empieza por 'á' -> debe agruparse bajo 'a'
    "ano",  # 'ano' y 'año' deben ser distintas (ñ es letra propia)
    "año",
    "a priori",  # locución (con espacio)
    "café",  # tilde final
    "casa",
    "ñandú",  # empieza por 'ñ'
    "ñoño",
    "ñoñería",  # ñ + tilde
    "perro",
    "zaherir",  # palabra poco común
    "-algia",  # sufijo (afijo con guion inicial)
    "supra-",  # prefijo (afijo con guion final)
    "ping-pong",  # guion interior: palabra compuesta, NO es afijo
    "Madrid",  # nombre propio
    "CD",  # sigla: va en mayúsculas pero NO es nombre propio
    "Bruselas",  # el par Bruselas/bruselas comparte forma normalizada
    "bruselas",
]


# Frecuencias de mentira pero verosímiles (escala Zipf). 0.0 = sin datos.
TEST_ZIPF = {
    "casa": 5.77,
    "año": 5.612,
    "perro": 4.91,
    "café": 4.6,
    "a priori": 3.5,
    "águila": 3.42,
    "ping-pong": 3.2,
    "ñoño": 2.6,
    "ano": 2.5,
    "ñandú": 2.12,
}


def _build_test_db() -> None:
    rows = [
        (
            w,
            normalize_word(w),
            first_letter(w),
            letter_count(w),
            1 if is_phrase(w) else 0,
            1 if is_affix(w) else 0,
            1 if is_proper(w) else 0,
        )
        for w in TEST_WORDS
    ]
    with get_connection() as conn:
        init_schema(conn)
        conn.executemany(
            "INSERT OR IGNORE INTO words "
            "(word, word_norm, first_letter, letter_count, is_phrase, is_affix, "
            "is_proper) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.executemany(
            "UPDATE words SET zipf = ?, freq_tier = ?, freq_source = 'test' WHERE word = ?",
            [(z, tier_for(z), w) for w, z in TEST_ZIPF.items()],
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('freq_sources', 'test') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )


_build_test_db()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    """Cliente desde loopback: una red interna (LEMARIO_TRUSTED_NETWORKS)."""
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture
def outside_client() -> TestClient:
    """Cliente desde una IP pública (documentación RFC 5737): fuera de las redes internas."""
    return TestClient(app, client=("203.0.113.9", 50000))


@pytest.fixture
def auth() -> dict:
    return {"X-API-Key": "testkey"}


@pytest.fixture(autouse=True)
def _clear_definitions_cache():
    """Vacía la caché de definiciones entre pruebas para aislarlas."""
    with get_connection() as conn:
        conn.execute("DELETE FROM definitions")
    yield


def pytest_addoption(parser):
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="Ejecuta también las pruebas marcadas como 'network'.",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network"):
        return
    skip = pytest.mark.skip(reason="necesita --run-network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
