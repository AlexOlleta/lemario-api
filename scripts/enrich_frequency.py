"""Añade la frecuencia de uso al índice: escala Zipf y nivel de dificultad.

Uso:
    python -m scripts.enrich_frequency                  # las tres fuentes
    python -m scripts.enrich_frequency --crea otra.txt  # otro fichero de CREA
    python -m scripts.enrich_frequency --no-crea        # sin CREA
    python -m scripts.enrich_frequency --local es_full.txt   # OpenSubtitles local

Tres fuentes, en este orden, y cada una entra solo donde la anterior no llega:

1. **CREA** (RAE, CC BY-SA 4.0). Es la única que cuenta **lemas** —su 'correr'
   incluye 'corría' y 'corrieron'—, que es exactamente lo que guarda este
   índice, y la única que **conserva las mayúsculas**: sabe que 'chile' (el ají,
   7,62 por millón) no es 'Chile' (el país, 90,70). Se descarga a mano y se deja
   en data/; no se pide por red. Su pega es la antigüedad: el corpus llega a
   2004, así que 'wifi' o 'tuitear' no existen para ella.
2. **wordfreq** (paquete Python, opcional). Mezcla subtítulos, Wikipedia, prensa
   y redes: aporta justo lo que a CREA le falta, lo moderno y lo multirregistro.
3. **OpenSubtitles 2018** (lista de hermitdave, CC BY-SA 3.0). La más larga
   —baja hasta palabras con una sola aparición—, para la cola.

Las de respaldo miden **formas** sueltas, no lemas, así que se quedan cortas de
forma sistemática; se recalibran a la escala de CREA (ver app/frequency.py) para
que un mismo nivel signifique lo mismo venga de donde venga.

Las palabras que no están en ninguna quedan en 'unknown', que no significa
"rarísima" sino "sin dato": son en su mayoría entradas del DLE que nadie usa.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Permite ejecutar como script suelto (python scripts/enrich_frequency.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.database import get_connection, init_schema  # noqa: E402
from app.frequency import (  # noqa: E402
    count_to_zipf,
    fpm_to_zipf,
    tier_for,
    to_crea_scale,
)

# Categoría de CREA para los signos de puntuación: no son palabras.
CREA_PUNCTUATION_TAG = "Y"


def load_wordfreq():
    """Devuelve zipf_frequency de wordfreq, o None si no está instalado."""
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        return None
    return zipf_frequency


def download_list(url: str) -> str:
    settings = get_settings()
    with httpx.Client(timeout=settings.http_timeout, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def parse_crea(text: str) -> dict[str, float]:
    """Lee el fichero de lemas de CREA. Devuelve apariciones por millón.

    Formato: elemento, categoría gramatical, frecuencia absoluta y dos
    normalizadas (con y sin signos ortográficos). Usamos la de **sin signos**,
    que es la que corresponde a un corpus de solo palabras.

    Las mayúsculas se conservan a propósito: son la única forma de distinguir
    'chile' de 'Chile'. Un mismo elemento aparece una vez por categoría
    gramatical ('que' como conjunción y como relativo), así que se suman.
    """
    per_million: dict[str, float] = {}
    for line in text.splitlines()[2:]:  # dos líneas de cabecera
        parts = line.split("\t")
        if len(parts) < 5 or not parts[2].strip().isdigit():
            continue
        if parts[1].strip() == CREA_PUNCTUATION_TAG:
            continue
        word = parts[0].strip()
        per_million[word] = per_million.get(word, 0.0) + float(parts[4])
    return per_million


def parse_counts(text: str) -> tuple[dict[str, int], int]:
    """Lee 'palabra apariciones' por línea. Devuelve (conteos, total del corpus).

    El total suma TODAS las apariciones, también las de formas que no están en
    el lemario: es el tamaño del corpus, y sin él no se puede calcular el Zipf.
    """
    counts: dict[str, int] = {}
    total = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2 or not parts[1].isdigit():
            continue
        count = int(parts[1])
        total += count
        # La lista trae mayúsculas y variantes: acumulamos por forma en minúscula.
        key = parts[0].lower()
        counts[key] = counts.get(key, 0) + count
    return counts, total


def resolve_zipf(
    word: str,
    crea: dict[str, float],
    zipf_frequency,
    counts: dict[str, int],
    corpus_total: int,
) -> tuple[float, str | None]:
    """Frecuencia de una palabra y de dónde sale. Devuelve (zipf, fuente).

    Si CREA solo conoce la palabra **en mayúscula** ('pedro' → 'Pedro'), se
    corta aquí y se deja sin dato: las otras dos fuentes ignoran las mayúsculas
    y le asignarían la frecuencia del nombre propio, que es justo el error que
    CREA permite evitar. Son 1.194 entradas, casi todas nombres y topónimos.
    """
    if crea:
        exact = crea.get(word)
        if exact:
            return fpm_to_zipf(exact), "crea"
        if word == word.lower() and (
            crea.get(word.capitalize()) or crea.get(word.upper())
        ):
            return 0.0, None

    if zipf_frequency is not None:
        zipf = zipf_frequency(word, "es")
        if zipf > 0:
            return to_crea_scale(zipf), "wordfreq"

    if counts:
        zipf = count_to_zipf(counts.get(word.lower(), 0), corpus_total)
        if zipf > 0:
            return to_crea_scale(zipf), "opensubtitles"

    return 0.0, None


def enrich(
    crea: dict[str, float],
    counts: dict[str, int],
    corpus_total: int,
    *,
    use_wordfreq: bool,
) -> dict:
    """Recalcula zipf/tier/fuente de todas las palabras. Devuelve estadísticas."""
    zipf_frequency = load_wordfreq() if use_wordfreq else None
    if use_wordfreq and zipf_frequency is None:
        print(
            "AVISO: wordfreq no está instalado (pip install wordfreq); "
            "se usarán solo las demás fuentes."
        )

    stats = {"crea": 0, "wordfreq": 0, "opensubtitles": 0, "unknown": 0}
    updates: list[tuple[float, str, str | None, int]] = []
    with get_connection() as conn:
        init_schema(conn)
        for row in conn.execute("SELECT id, word FROM words").fetchall():
            zipf, source = resolve_zipf(
                row["word"], crea, zipf_frequency, counts, corpus_total
            )
            stats[source or "unknown"] += 1
            updates.append((zipf, tier_for(zipf), source, row["id"]))

        conn.executemany(
            "UPDATE words SET zipf = ?, freq_tier = ?, freq_source = ? WHERE id = ?",
            updates,
        )
        sources = ",".join(
            name
            for name, used in (
                ("crea", bool(crea)),
                ("wordfreq", zipf_frequency is not None),
                ("opensubtitles", bool(counts)),
            )
            if used
        )
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            [
                ("freq_sources", sources),
                ("freq_updated_at", datetime.now(timezone.utc).isoformat()),
            ],
        )
    stats["total"] = len(updates)
    return stats


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Añade frecuencia de uso (Zipf) al índice de Lemario."
    )
    parser.add_argument("--crea", help="Fichero de lemas de CREA (por defecto, el de data/).")
    parser.add_argument("--no-crea", action="store_true", help="No usar CREA.")
    parser.add_argument(
        "--local", help="Fichero local de OpenSubtitles ('palabra apariciones')."
    )
    parser.add_argument(
        "--no-wordfreq", action="store_true", help="No usar el paquete wordfreq."
    )
    parser.add_argument(
        "--no-opensubtitles",
        action="store_true",
        help="No usar la lista de OpenSubtitles (ni descargarla).",
    )
    args = parser.parse_args(argv)

    db = Path(settings.database_path)
    if not db.exists():
        print(f"No hay índice en {db}. Ejecuta antes scripts/build_index.py.")
        return 1

    crea: dict[str, float] = {}
    if not args.no_crea:
        crea_path = Path(args.crea or settings.crea_path)
        if crea_path.exists():
            print(f"Leyendo CREA: {crea_path}")
            crea = parse_crea(crea_path.read_text(encoding="utf-8"))
            print(f"  {len(crea):,} lemas.")
        else:
            print(
                f"AVISO: no está {crea_path}; se sigue sin CREA. "
                "Descárgala de la RAE y déjala ahí para la mejor fuente."
            )

    counts: dict[str, int] = {}
    total = 0
    if not args.no_opensubtitles:
        if args.local:
            print(f"Leyendo lista local: {args.local}")
            text = Path(args.local).read_text(encoding="utf-8")
        else:
            print(f"Descargando lista de frecuencias: {settings.freq_list_url}")
            text = download_list(settings.freq_list_url)
        counts, total = parse_counts(text)
        print(f"  {len(counts):,} formas, {total:,} palabras de corpus.")

    print("Calculando frecuencias...")
    stats = enrich(crea, counts, total, use_wordfreq=not args.no_wordfreq)
    known = stats["total"] - stats["unknown"]
    print(
        f"Listo. {known:,} de {stats['total']:,} palabras con frecuencia "
        f"({known / stats['total'] * 100:.1f}%): "
        f"{stats['crea']:,} de CREA, "
        f"{stats['wordfreq']:,} de wordfreq, "
        f"{stats['opensubtitles']:,} de OpenSubtitles, "
        f"{stats['unknown']:,} sin datos."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
