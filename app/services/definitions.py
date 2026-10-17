"""Obtención de definiciones: caché local -> rae-api.com -> scraping dle.rae.es."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from urllib.parse import quote, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from ..config import get_settings
from ..database import database_exists, get_connection
from ..models import Definition, Sense
from ..normalize import normalize_word

logger = logging.getLogger("lemario.definitions")


class WordNotFound(Exception):
    """La palabra no se encontró en ninguna fuente."""


class SourceUnavailable(Exception):
    """Ninguna fuente externa respondió correctamente."""


def _load_from_cache(word_norm: str) -> Definition | None:
    # Sin índice no hay BD: abrirla en solo-lectura daría un 500.
    if not database_exists():
        return None
    with get_connection(read_only=True) as conn:
        row = conn.execute(
            "SELECT word, source, data, fetched_at FROM definitions WHERE word_norm = ?",
            (word_norm,),
        ).fetchone()
    if not row:
        return None
    senses = [Sense(**s) for s in json.loads(row["data"])]
    return Definition(
        word=row["word"],
        source="cache",
        cached=True,
        senses=senses,
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
    )


def _save_to_cache(definition: Definition) -> None:
    payload = json.dumps([s.model_dump() for s in definition.senses], ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO definitions (word, word_norm, source, data, fetched_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(word) DO UPDATE SET "
            "source=excluded.source, data=excluded.data, fetched_at=excluded.fetched_at",
            (
                definition.word,
                normalize_word(definition.word),
                definition.source,
                payload,
                definition.fetched_at.isoformat(),
            ),
        )


_MAX_REDIRECTS = 3


def _source_url(base: str, word: str) -> str:
    """La palabra va como un único segmento: un '?', '#' o '..' no alteran la ruta."""
    return f"{base}/{quote(word, safe='')}"


async def _get_same_host(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET que solo sigue redirecciones al mismo host; si salen de él, devuelve la 3xx."""
    host = urlsplit(url).hostname
    for _ in range(_MAX_REDIRECTS + 1):
        resp = await client.get(url)
        if not resp.is_redirect:
            return resp
        target = urljoin(url, resp.headers.get("location", ""))
        parts = urlsplit(target)
        if parts.scheme not in ("http", "https") or parts.hostname != host:
            return resp
        url = target
    return resp


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    """GET con reintentos. Devuelve None si agota los reintentos por error de red."""
    settings = get_settings()
    last_exc: Exception | None = None
    for attempt in range(settings.http_retries + 1):
        try:
            return await _get_same_host(client, url)
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning("Fallo al pedir %s (intento %d): %s", url, attempt + 1, exc)
            await asyncio.sleep(0.4 * (attempt + 1))
    logger.error("Agotados los reintentos para %s: %s", url, last_exc)
    return None


def _parse_rae_api(payload: dict) -> list[Sense]:
    senses: list[Sense] = []
    data = payload.get("data") or {}
    groups = (data.get("meanings") or []) + (data.get("locutions") or [])
    for group in groups:
        for sense in group.get("senses") or []:
            text = (sense.get("description") or sense.get("raw") or "").strip()
            if not text:
                continue
            number = sense.get("meaning_number")
            senses.append(
                Sense(
                    number=str(number) if number is not None else None,
                    category=sense.get("category"),
                    description=text,
                )
            )
    return senses


async def _fetch_rae_api(client: httpx.AsyncClient, word: str) -> list[Sense] | None:
    settings = get_settings()
    url = _source_url(settings.rae_api_base, word)
    resp = await _get(client, url)
    if resp is None:
        raise SourceUnavailable("rae-api.com no respondió")
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise SourceUnavailable(f"rae-api.com devolvió {resp.status_code}")
    try:
        payload = resp.json()
    except json.JSONDecodeError:
        raise SourceUnavailable("rae-api.com devolvió un JSON inválido") from None
    if not payload.get("ok", True) and not payload.get("data"):
        return None
    senses = _parse_rae_api(payload)
    return senses or None


# Una acepción del DLE empieza por "N. abrev." (p. ej. "1. tr.").
_SENSE_RE = re.compile(r"^\s*\d+\.\s")


def _parse_dle_html(html: str) -> list[Sense]:
    """Extrae acepciones del HTML de dle.rae.es (marcado clásico y nuevo)."""
    soup = BeautifulSoup(html, "lxml")

    # Marcado clásico: cada acepción es un <p> cuya clase empieza por 'j'.
    classic = [
        Sense(description=tag.get_text(" ", strip=True))
        for tag in soup.find_all("p", class_=lambda c: bool(c) and c[0].startswith("j"))
        if tag.get_text(strip=True)
    ]
    if classic:
        return classic

    # Marcado nuevo: acepciones numeradas, sin depender de clases ofuscadas.
    article = soup.find("article") or soup
    senses: list[Sense] = []
    seen: set[str] = set()
    for tag in article.find_all(["li", "p"]):
        text = tag.get_text(" ", strip=True)
        if text and len(text) > 6 and _SENSE_RE.match(text) and text not in seen:
            seen.add(text)
            senses.append(Sense(description=text))
    return senses


async def _fetch_dle(client: httpx.AsyncClient, word: str) -> list[Sense] | None:
    settings = get_settings()
    url = _source_url(settings.dle_base, word)
    resp = await _get(client, url)
    if resp is None:
        raise SourceUnavailable("dle.rae.es no respondió")
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise SourceUnavailable(f"dle.rae.es devolvió {resp.status_code}")
    senses = _parse_dle_html(resp.text)
    return senses or None


async def get_definition(word: str, *, force: bool = False) -> Definition:
    """Caché -> rae-api.com -> scraping de dle.rae.es; cachea lo que encuentra.

    Lanza WordNotFound si ninguna fuente la conoce y SourceUnavailable si no responden.
    """
    settings = get_settings()
    word = word.strip()
    norm = normalize_word(word)

    if not force:
        cached = _load_from_cache(norm)
        if cached is not None:
            return cached

    # dle.rae.es responde 403 a lo que no parece un navegador.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9",
    }
    timeout = httpx.Timeout(settings.http_timeout)
    unavailable: list[str] = []

    async with httpx.AsyncClient(
        timeout=timeout, headers=headers, follow_redirects=False
    ) as client:
        try:
            senses = await _fetch_rae_api(client, word)
            if senses is not None:
                definition = Definition(
                    word=word,
                    source="rae-api",
                    cached=False,
                    senses=senses,
                    fetched_at=datetime.now(UTC),
                )
                _save_to_cache(definition)
                return definition
        except SourceUnavailable as exc:
            unavailable.append(str(exc))

        try:
            senses = await _fetch_dle(client, word)
            if senses is not None:
                definition = Definition(
                    word=word,
                    source="dle.rae.es",
                    cached=False,
                    senses=senses,
                    fetched_at=datetime.now(UTC),
                )
                _save_to_cache(definition)
                return definition
        except SourceUnavailable as exc:
            unavailable.append(str(exc))

    if unavailable:
        raise SourceUnavailable("; ".join(unavailable))
    raise WordNotFound(word)
