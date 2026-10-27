"""Instancia compartida del limitador de tasa (slowapi)."""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import get_settings

# Tras un proxy, uvicorn sustituye request.client por la IP real si confía en él.
# key_style="endpoint": un contador por función, no por URL; con "url" (el valor
# por defecto) cada palabra de /words/exists/{word} tendría su propio contador.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[get_settings().rate_limit_default],
    storage_uri=get_settings().rate_limit_storage,
    key_style="endpoint",
)


def default_rate_limit(request: Request) -> None:
    """Aplica el límite por defecto a las rutas sin límite propio.

    Sustituye a SlowAPIMiddleware: desde FastAPI 0.143 las rutas de los routers
    no aparecen en app.routes y el middleware las dejaba sin límite. Como
    dependencia, la ruta ya está resuelta en request.scope["endpoint"]. Las rutas
    con @limiter.limit las limita su decorador.
    """
    endpoint = request.scope.get("endpoint")
    if endpoint is None:
        return
    if f"{endpoint.__module__}.{endpoint.__name__}" in limiter._route_limits:
        return
    limiter._check_request_limit(request, endpoint, in_middleware=True)
