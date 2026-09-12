"""Autenticación por API key."""

from __future__ import annotations

import logging
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import get_settings

logger = logging.getLogger("lemario.security")

# Esquema de seguridad: hace que aparezca el botón "Authorize" en /docs con el
# nombre de cabecera configurado. auto_error=False para poder permitir el modo
# abierto (sin claves) sin que FastAPI rechace antes de comprobarlo.
_api_key_scheme = APIKeyHeader(
    name=get_settings().api_key_header,
    auto_error=False,
    description="Clave de API. Debe coincidir con una de LEMARIO_API_KEYS.",
)


def require_api_key(provided: str | None = Security(_api_key_scheme)) -> None:
    """Dependencia FastAPI: valida la API key si hay claves configuradas.

    Si no hay ninguna clave configurada, la API queda abierta (modo dev) y se
    registra un aviso. En producción, define LEMARIO_API_KEYS.
    """
    settings = get_settings()
    if not settings.security_enabled:
        logger.warning(
            "API sin claves configuradas: acceso abierto. Define LEMARIO_API_KEYS."
        )
        return

    # Comparación en tiempo constante contra cada clave válida.
    for valid in settings.api_keys:
        if secrets.compare_digest(provided or "", valid):
            return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API key inválida o ausente.",
        headers={"WWW-Authenticate": settings.api_key_header},
    )
