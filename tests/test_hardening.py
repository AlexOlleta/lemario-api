"""Pruebas de endurecimiento: redes internas, producción, URLs externas."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services import definitions

DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_available_from_internal_network(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_hidden_from_outside(outside_client, path):
    # 404 y no 403: no se delata que la ruta exista.
    assert outside_client.get(path).status_code == 404


def test_openapi_lists_the_api_but_not_the_docs_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/words/rhymes" in paths
    assert "/docs" not in paths and "/openapi.json" not in paths


def test_health_detail_only_for_internal_network(client, outside_client):
    inside = client.get("/health").json()
    assert inside["word_count"] == 18 and "version" in inside and "security_enabled" in inside
    outside = outside_client.get("/health")
    assert outside.status_code == 200
    assert outside.json() == {"status": "ok", "index_ready": True}


def test_non_ip_client_is_not_trusted():
    from starlette.requests import Request

    from app.security import is_trusted_client

    def request_from(host):
        return Request({"type": "http", "client": (host, 1), "headers": []})

    assert is_trusted_client(request_from("127.0.0.1"))
    assert is_trusted_client(request_from("::1"))
    assert is_trusted_client(request_from("::ffff:127.0.0.1"))
    assert not is_trusted_client(request_from("testclient"))
    assert not is_trusted_client(request_from("10.0.0.5"))
    assert not is_trusted_client(Request({"type": "http", "client": None, "headers": []}))


def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_production_requires_api_keys():
    with pytest.raises(ValidationError, match="LEMARIO_API_KEYS"):
        # api_keys explícito: el entorno de las pruebas ya define LEMARIO_API_KEYS.
        _settings(environment="production", api_keys=[], cors_origins=["https://example.org"])


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError, match="CORS"):
        _settings(environment="production", api_keys=["k"], cors_origins=["*"])


def test_production_accepts_secure_config():
    s = _settings(environment="production", api_keys=["k"], cors_origins=["https://example.org"])
    assert s.environment == "production"


def test_development_stays_permissive():
    s = _settings(api_keys=[])
    assert s.environment == "development" and not s.security_enabled


def test_trusted_networks_accept_csv_and_reject_garbage():
    assert [str(n) for n in _settings(trusted_networks="10.0.0.0/8, ::1/128").trusted_nets] == [
        "10.0.0.0/8",
        "::1/128",
    ]
    with pytest.raises(ValidationError):
        _settings(trusted_networks="no-es-una-red")


@pytest.mark.parametrize(
    "word,expected",
    [
        ("casa", "https://x.test/api/casa"),
        ("año", "https://x.test/api/a%C3%B1o"),
        ("a?b=1", "https://x.test/api/a%3Fb%3D1"),
        ("../admin", "https://x.test/api/..%2Fadmin"),
        ("a#b", "https://x.test/api/a%23b"),
    ],
)
def test_source_url_is_a_single_encoded_segment(word, expected):
    assert definitions._source_url("https://x.test/api", word) == expected


def _client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


def _get(handler, url):
    async def run():
        async with _client_with(handler) as client:
            return await definitions._get_same_host(client, url)

    return asyncio.run(run())


def test_redirect_within_same_host_is_followed():
    def handler(request):
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "https://x.test/b"})
        return httpx.Response(200, text="ok")

    resp = _get(handler, "https://x.test/a")
    assert resp.status_code == 200 and resp.text == "ok"


def test_redirect_to_other_host_is_not_followed():
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    resp = _get(handler, "https://x.test/a")
    assert resp.status_code == 302
    assert seen == ["x.test"]  # jamás se pidió el otro host


def test_redirect_loop_is_bounded():
    def handler(request):
        return httpx.Response(302, headers={"location": "https://x.test/loop"})

    resp = _get(handler, "https://x.test/loop")
    assert resp.status_code == 302
