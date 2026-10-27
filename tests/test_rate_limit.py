"""Pruebas del límite de tasa: que se aplique de verdad a cada ruta."""

from __future__ import annotations

import pytest
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.limiter import limiter


def _route_limits(value: str) -> list:
    """Límites de ruta como los que crea @limiter.limit, para un valor como "3/minute"."""
    tmp = Limiter(key_func=get_remote_address)

    @tmp.limit(value)
    def endpoint(request):  # pragma: no cover - solo se usa para registrar el límite
        return None

    return tmp._route_limits[f"{endpoint.__module__}.{endpoint.__name__}"]


@pytest.fixture
def low_limits(monkeypatch):
    """Límite por defecto y de /words/exists a 3/minute, con contadores limpios."""
    monkeypatch.setattr(
        limiter,
        "_default_limits",
        Limiter(key_func=get_remote_address, default_limits=["3/minute"])._default_limits,
    )
    for name in ("app.routers.words.exists", "app.routers.words.exists_batch"):
        monkeypatch.setitem(limiter._route_limits, name, _route_limits("3/minute"))
    limiter.reset()
    yield
    limiter.reset()


def _statuses(client, auth, paths) -> list[int]:
    return [client.get(path, headers=auth).status_code for path in paths]


@pytest.mark.parametrize("path", ["/words/random", "/words/rhymes?ending=asa", "/", "/health"])
def test_default_limit_applies_to_every_route(low_limits, client, auth, path):
    # Las rutas de los routers se quedaban sin límite con SlowAPIMiddleware.
    assert _statuses(client, auth, [path] * 4) == [200, 200, 200, 429]


def test_route_limit_is_shared_across_urls(low_limits, client, auth):
    # Un contador por endpoint: cambiar de palabra no da peticiones nuevas.
    paths = ["/words/exists/casa", "/words/exists/perro", "/words/exists/año", "/words/exists/ñoño"]
    assert _statuses(client, auth, paths) == [200, 200, 200, 429]


def test_routes_with_own_limit_skip_the_default(low_limits, client, auth):
    # /words/exists tiene su límite propio; no debe sumarse al de /words/random.
    assert _statuses(client, auth, ["/words/random"] * 3) == [200, 200, 200]
    assert _statuses(client, auth, ["/words/exists/casa"]) == [200]


def test_limits_are_per_client(low_limits, client, outside_client, auth):
    assert _statuses(client, auth, ["/words/random"] * 4)[-1] == 429
    assert _statuses(outside_client, auth, ["/words/random"]) == [200]
