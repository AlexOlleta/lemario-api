"""Instancia compartida del limitador de tasa (slowapi)."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from .config import get_settings

# Tras un proxy, uvicorn sustituye request.client por la IP real si confía en él.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[get_settings().rate_limit_default],
    storage_uri=get_settings().rate_limit_storage,
)
