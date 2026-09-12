"""Aplicación FastAPI de Lemario."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import __version__
from .config import get_settings
from .database import database_exists, get_connection, migrate
from .limiter import limiter
from .routers import definitions, words

logging.basicConfig(level=logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pone al día el esquema de una base construida con una versión anterior.

    Es barato (no hace nada si ya está al día) y evita que un índice antiguo
    rompa las consultas. Si la base es de solo lectura, se avisa y se sigue:
    el arranque nunca debe depender de poder escribir.
    """
    if database_exists():
        try:
            with get_connection() as conn:
                migrate(conn)
        except Exception:  # noqa: BLE001 - migrar es best-effort
            logging.warning("No se pudo migrar el esquema del índice.", exc_info=True)
    yield


app = FastAPI(
    title="Lemario",
    lifespan=lifespan,
    version=__version__,
    description=(
        "API para obtener palabras en español del lemario de la RAE "
        "(por letra, por longitud, aleatoria) y sus definiciones."
    ),
)

# --- Rate limiting (slowapi) ---
# default_limits del limiter se aplican a todas las rutas mediante el middleware.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials="*" not in settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(words.router)
app.include_router(definitions.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Estado del servicio e información del índice (sin autenticación)."""
    info: dict = {
        "status": "ok",
        "version": __version__,
        "security_enabled": settings.security_enabled,
        "index_ready": database_exists(),
    }
    if database_exists():
        try:
            with get_connection(read_only=True) as conn:
                info["word_count"] = conn.execute(
                    "SELECT COUNT(*) FROM words"
                ).fetchone()[0]
                row = conn.execute(
                    "SELECT value FROM meta WHERE key = 'list_file'"
                ).fetchone()
                info["list_file"] = row["value"] if row else None
                row = conn.execute(
                    "SELECT value FROM meta WHERE key = 'freq_sources'"
                ).fetchone()
                # None = índice sin frecuencias (no se puede filtrar por tier).
                info["freq_sources"] = row["value"] if row else None
        except Exception:  # noqa: BLE001 - el healthcheck nunca debe romper
            info["index_ready"] = False
    return info


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"name": "Lemario", "docs": "/docs", "health": "/health"}
