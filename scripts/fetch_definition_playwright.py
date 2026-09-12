"""MODO PRUEBA — Extrae definiciones de dle.rae.es con un navegador real.

La API normal usa rae-api.com (fiable) y deja dle.rae.es como respaldo HTTP
"best-effort", que la RAE bloquea con 403 (Cloudflare). Este script es una
PRUEBA independiente que demuestra cómo obtener la definición directamente de
la web oficial usando Playwright (Chromium headless), que sí ejecuta el reto
de Cloudflare como lo haría un navegador.

NO está integrado en la API: sirve para experimentar / comparar.

Requisitos:
    pip install -r requirements-dev.txt
    playwright install chromium

Uso:
    python -m scripts.fetch_definition_playwright casa
    python -m scripts.fetch_definition_playwright "zaherir" --headed --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Permite ejecutarlo como script suelto y reutilizar el parser de la app.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.services.definitions import _parse_dle_html  # noqa: E402


class CloudflareBlocked(Exception):
    """No se pudo superar el reto de Cloudflare."""


def _is_challenge(html: str) -> bool:
    return "ray-id" in html or "Un momento" in html or "challenge-platform" in html


def fetch_definition(
    word: str,
    *,
    headed: bool = False,
    timeout_ms: int = 30000,
    attempts: int = 4,
):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(
            "Playwright no está instalado. Ejecuta:\n"
            "  pip install -r requirements-dev.txt\n"
            "  playwright install chromium"
        )

    settings = get_settings()
    url = f"{settings.dle_base}/{word}"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not headed,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            locale="es-ES",
            timezone_id="Europe/Madrid",
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        # Pequeño parche anti-detección.
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        page = context.new_page()

        resolved = False
        html = ""
        for _ in range(attempts):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception:  # noqa: BLE001 - reintentamos
                continue
            # Sondea hasta que el reto de Cloudflare se resuelva y aparezca el
            # artículo (o se agote el tiempo de este intento).
            for _ in range(int(timeout_ms / 600)):
                html = page.content()
                if not _is_challenge(html) and "<article" in html:
                    resolved = True
                    break
                page.wait_for_timeout(600)
            if resolved:
                break
            page.wait_for_timeout(1500)  # enfría antes de recargar

        browser.close()

    if not resolved:
        raise CloudflareBlocked(
            "Cloudflare bloqueó la petición (reto sin resolver). En headless suele "
            "fallar desde IPs señaladas; prueba con --headed y una IP normal."
        )

    senses = _parse_dle_html(html)
    return [s.model_dump() for s in senses]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PRUEBA: extrae definiciones de dle.rae.es con Playwright."
    )
    parser.add_argument("word", help="Palabra a buscar.")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Muestra el navegador (útil para depurar el reto de Cloudflare).",
    )
    parser.add_argument("--json", action="store_true", help="Salida en JSON.")
    args = parser.parse_args(argv)

    try:
        senses = fetch_definition(args.word, headed=args.headed)
    except CloudflareBlocked as exc:
        print(f"[Cloudflare] {exc}")
        return 2

    if not senses:
        print(
            f"No se encontró definición para '{args.word}' "
            "(palabra inexistente o cambió el marcado de dle.rae.es)."
        )
        return 1

    if args.json:
        print(json.dumps({"word": args.word, "senses": senses}, ensure_ascii=False, indent=2))
    else:
        print(f"Definiciones de '{args.word}':")
        for i, s in enumerate(senses, 1):
            print(f"  {i}. {s['description']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
