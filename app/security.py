"""Autenticación por API key y restricción a redes internas."""

from __future__ import annotations

import ipaddress
import secrets

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from .config import get_settings

# auto_error=False: sin claves configuradas la API queda abierta (solo desarrollo).
_api_key_scheme = APIKeyHeader(
    name=get_settings().api_key_header,
    auto_error=False,
    description="Clave de API. Debe coincidir con una de LEMARIO_API_KEYS.",
)


def is_trusted_client(request: Request) -> bool:
    """¿Viene de LEMARIO_TRUSTED_NETWORKS? Tras un proxy no confiado, la IP es la del proxy."""
    host = request.client.host if request.client else None
    try:
        ip = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip in net for net in get_settings().trusted_nets)


def require_trusted_network(request: Request) -> None:
    """404 y no 403, para no delatar que la ruta existe."""
    if not is_trusted_client(request):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def require_api_key(provided: str | None = Security(_api_key_scheme)) -> None:
    """Valida la API key si hay claves configuradas."""
    settings = get_settings()
    if not settings.security_enabled:
        return

    for valid in settings.api_keys:
        if secrets.compare_digest(provided or "", valid):
            return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="API key inválida o ausente.",
        headers={"WWW-Authenticate": settings.api_key_header},
    )
