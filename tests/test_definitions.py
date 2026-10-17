"""Pruebas del servicio y endpoint de definiciones.

Las fuentes externas se simulan (mock) para que las pruebas sean deterministas
y no dependan de la red. Hay además una prueba real opcional (--run-network)
para una palabra poco común.
"""

from __future__ import annotations

import pytest

from app.models import Sense
from app.services import definitions
from app.services.definitions import SourceUnavailable


def test_parse_rae_api():
    payload = {
        "ok": True,
        "data": {
            "meanings": [
                {
                    "senses": [
                        {
                            "meaning_number": 1,
                            "category": "noun",
                            "description": "Edificio para habitar",
                        }
                    ]
                }
            ]
        },
    }
    senses = definitions._parse_rae_api(payload)
    assert len(senses) == 1
    assert senses[0].number == "1"
    assert senses[0].description == "Edificio para habitar"


def test_parse_dle_html():
    html = (
        "<html><body>"
        '<p class="j1">1. f. Pieza de prueba.</p>'
        '<p class="l">enlace irrelevante</p>'
        '<p class="j2">2. f. Segunda acepción.</p>'
        "</body></html>"
    )
    senses = definitions._parse_dle_html(html)
    assert len(senses) == 2
    assert "prueba" in senses[0].description


def test_definition_from_rae_then_cache(client, auth, monkeypatch):
    calls = {"n": 0}

    async def fake_rae(_client, word):
        calls["n"] += 1
        return [Sense(number="1", category="noun", description="Bebida de café")]

    monkeypatch.setattr(definitions, "_fetch_rae_api", fake_rae)

    r = client.get("/definitions/café", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "rae-api"
    assert body["cached"] is False

    r2 = client.get("/definitions/café", headers=auth)
    assert r2.json()["source"] == "cache"
    assert r2.json()["cached"] is True
    assert calls["n"] == 1


def test_definition_falls_back_to_dle(client, auth, monkeypatch):
    async def fail_rae(_client, word):
        raise SourceUnavailable("rae-api caído")

    async def ok_dle(_client, word):
        return [Sense(description="Definición vía dle.rae.es")]

    monkeypatch.setattr(definitions, "_fetch_rae_api", fail_rae)
    monkeypatch.setattr(definitions, "_fetch_dle", ok_dle)

    r = client.get("/definitions/zaherir", headers=auth)
    assert r.status_code == 200
    assert r.json()["source"] == "dle.rae.es"


def test_accent_insensitive_lookup_returns_official_spelling(client, auth, monkeypatch):
    """Buscar 'cafe' (sin tilde) debe resolver a la grafía oficial 'café'."""
    received = {}

    async def fake_rae(_client, word):
        received["word"] = word
        return [Sense(description="x")]

    monkeypatch.setattr(definitions, "_fetch_rae_api", fake_rae)

    r = client.get("/definitions/cafe", headers=auth)
    assert r.status_code == 200
    assert r.json()["word"] == "café"
    assert received["word"] == "café"


def test_rare_word_not_found(client, auth, monkeypatch):
    """Palabra del lemario pero sin definición en ninguna fuente -> 404."""

    async def none_rae(_client, word):
        return None

    async def none_dle(_client, word):
        return None

    monkeypatch.setattr(definitions, "_fetch_rae_api", none_rae)
    monkeypatch.setattr(definitions, "_fetch_dle", none_dle)

    r = client.get("/definitions/zaherir", headers=auth)
    assert r.status_code == 404


def test_word_not_in_lemario_is_rejected(client, auth):
    r = client.get("/definitions/asdfghjk", headers=auth)
    assert r.status_code == 404
    assert "lemario" in r.json()["detail"].lower()


def test_sources_unavailable_returns_502(client, auth, monkeypatch):
    async def down_rae(_client, word):
        raise SourceUnavailable("rae-api caído")

    async def down_dle(_client, word):
        raise SourceUnavailable("dle.rae.es 403")

    monkeypatch.setattr(definitions, "_fetch_rae_api", down_rae)
    monkeypatch.setattr(definitions, "_fetch_dle", down_dle)

    r = client.get("/definitions/zaherir", headers=auth)
    assert r.status_code == 502


def test_load_from_cache_without_db(monkeypatch):
    """Sin índice, la caché debe comportarse como vacía (no lanzar 500)."""
    monkeypatch.setattr(definitions, "database_exists", lambda: False)
    assert definitions._load_from_cache("loquesea") is None


@pytest.mark.network
def test_real_rare_word_definition(client, auth):
    r = client.get("/definitions/inefable?require_in_list=false", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["source"] in {"rae-api", "dle.rae.es"}
    assert len(body["senses"]) >= 1
