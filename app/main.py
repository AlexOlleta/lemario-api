"""Aplicación FastAPI de Lemario."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import __version__
from .config import get_settings
from .database import database_exists, get_connection, migrate
from .limiter import default_rate_limit, limiter
from .routers import definitions, words
from .security import is_trusted_client, require_trusted_network

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lemario")

settings = get_settings()


def _warn_about_setup() -> None:
    """Avisos de configuración, una vez al arrancar."""
    if not settings.security_enabled:
        logger.warning(
            "API sin claves configuradas: acceso abierto. Define LEMARIO_API_KEYS "
            "(en LEMARIO_ENVIRONMENT=production es obligatorio)."
        )
    workers = os.environ.get("WEB_CONCURRENCY", "1")
    if workers.isdigit() and int(workers) > 1 and settings.rate_limit_storage.startswith("memory"):
        logger.warning(
            "Hay %s workers pero el límite de tasa cuenta en memoria: cada worker "
            "cuenta aparte. Define LEMARIO_RATE_LIMIT_STORAGE=redis://...",
            workers,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Migra el esquema de un índice antiguo; si no se puede escribir, avisa y sigue."""
    _warn_about_setup()
    if database_exists():
        try:
            with get_connection() as conn:
                migrate(conn)
        except Exception:
            logger.warning("No se pudo migrar el esquema del índice.", exc_info=True)
    yield


# La documentación se sirve a mano más abajo para restringirla a redes internas.
app = FastAPI(
    title="Lemario",
    lifespan=lifespan,
    version=__version__,
    dependencies=[Depends(default_rate_limit)],
    description=(
        "API para obtener palabras en español del lemario de la RAE "
        "(por letra, por longitud, aleatoria) y sus definiciones."
    ),
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials="*" not in settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(words.router)
app.include_router(definitions.router)

internal = APIRouter(dependencies=[Depends(require_trusted_network)], include_in_schema=False)


@internal.get("/openapi.json")
def openapi_json() -> dict:
    return app.openapi()


@internal.get("/docs")
def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Swagger UI")


@internal.get("/redoc")
def redoc() -> HTMLResponse:
    return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} - ReDoc")


app.include_router(internal)


def _meta(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


@app.get("/health", tags=["meta"])
def health(request: Request) -> dict:
    """Estado del servicio, sin autenticación.

    Desde fuera solo dice si el servicio está vivo y el índice listo; el detalle
    (versión, tamaño del índice, fuentes) se reserva a las redes internas.
    """
    ready = database_exists()
    detail: dict = {}
    if ready:
        try:
            with get_connection(read_only=True) as conn:
                detail["word_count"] = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
                detail["list_file"] = _meta(conn, "list_file")
                # None = índice sin frecuencias (no se puede filtrar por tier).
                detail["freq_sources"] = _meta(conn, "freq_sources")
                # None = sin femeninos derivados (scripts/derive_feminines.py).
                detail["derived_source"] = _meta(conn, "derived_source")
        except Exception:  # noqa: BLE001 - el healthcheck nunca debe romper
            ready = False
            detail = {}
    if not is_trusted_client(request):
        return {"status": "ok", "index_ready": ready}
    return {
        "status": "ok",
        "version": __version__,
        "security_enabled": settings.security_enabled,
        "index_ready": ready,
        **detail,
    }


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"name": "Lemario", "docs": "/docs", "health": "/health"}
