"""Añade al índice los femeninos que el lemario no trae ('lógica' de 'lógico').

Uso:
    python -m scripts.derive_feminines                    # Hunspell + corpus + RAE
    python -m scripts.derive_feminines --no-rae           # sin consultar a la RAE
    python -m scripts.derive_feminines --local es_full.txt   # OpenSubtitles local

El listado de la RAE guarda cada entrada con su primera forma: 'lógico, ca'
queda como 'lógico', y ni 'lógica' ni 'niña' existen para la API. Este script
las añade como formas **derivadas** (is_derived = 1, base_word = el lema), sin
mezclarlas con los lemas oficiales. Va después de build_index (que borra la
tabla de palabras) y antes de enrich_frequency (para que tengan frecuencia).

Quién decide si un lema tiene femenino:

1. **Hunspell es_ES**, si conoce el lema: su marca 'G' significa "tiene
   femenino" ('lógico/SGk' sí, 'pórtico/S' no). Hay que descargarlo antes con
   scripts/fetch_hunspell.py.
2. Si Hunspell no lo conoce, solo las **esdrújulas en -ico** ('tautológico'),
   que en el DLE son casi siempre "-ico, ca". Se confirman con el corpus
   (OpenSubtitles o wordfreq) y, si no aparecen, preguntando a rae-api.com.
   Las respuestas se guardan en LEMARIO_RAE_CHECK_CACHE: la primera vez son
   unas 930 consultas. Sin clave, la cuota de rae-api (100 al día) se agota
   enseguida y el script espera a que se renueve, así que lleva días; con la
   clave gratuita (LEMARIO_RAE_CHECK_API_KEY) basta con unos minutos. Si se
   corta, se reanuda donde se quedó y nunca se repite una consulta.
3. El resto de lemas que Hunspell no conoce y que **podrían** tener femenino
   por su terminación no se añaden: se apunta el femenino posible en
   feminine_candidate, sin confirmar, como punto de partida para el futuro.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import httpx

# Permite ejecutar como script suelto (python scripts/derive_feminines.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.database import get_connection, init_schema
from app.normalize import first_letter, letter_count, normalize_word
from scripts.enrich_frequency import download_list, load_wordfreq, parse_counts
from scripts.fetch_hunspell import SOURCE_FILE

# Reglas singulares de "SFX G" en el index.aff de Hunspell: (quitar, poner).
# Falta a propósito '-e' > '-a': da 'presidenta', pero también 'transparenta'.
FEMININE_RULES = (
    ("que", "ca"),
    ("o", "a"),
    ("án", "ana"),
    ("ín", "ina"),
    ("ón", "ona"),
    ("és", "esa"),
    ("ós", "osa"),
)
# Y tras estas consonantes se añade '-a': 'profesor' > 'profesora'.
CONSONANTS_PLUS_A = "dlrz"

ACCENTED = set("áéíóú")

# Evidencia mínima en el corpus para dar por buena una esdrújula sin preguntar.
MIN_COUNT = 3
MIN_ZIPF = 1.0

# Esperas seguidas por límite de tasa antes de dar una palabra por perdida.
MAX_RATE_LIMIT_WAITS = 5


def parse_dic(text: str) -> dict[str, set[str]]:
    """Lee un .dic de Hunspell. Devuelve las marcas de cada palabra.

    La primera línea es el número de entradas. Una palabra puede repetirse con
    marcas distintas ('bonito/GS' y 'bonito/S'): se unen.
    """
    flags: dict[str, set[str]] = {}
    for line in text.splitlines()[1:]:
        word, _, marks = line.strip().partition("/")
        if word:
            flags.setdefault(word, set()).update(marks)
    return flags


def feminine_form(word: str) -> str | None:
    """El femenino según las reglas de Hunspell, o None si la terminación no tiene."""
    for strip, add in FEMININE_RULES:
        if word.endswith(strip):
            return word[: -len(strip)] + add
    if word[-1:] in CONSONANTS_PLUS_A:
        return word + "a"
    return None


def is_esdrujula_ico(word: str) -> bool:
    """'lógico', 'químico': terminan en -ico con la tilde antes ('abanico' no)."""
    return word.endswith("ico") and bool(ACCENTED & set(word[:-3]))


def classify(word: str, flags: set[str] | None) -> tuple[str, str] | None:
    """Qué hacer con un lema. Devuelve (vía, femenino) o None si no tiene.

    Vías: 'hunspell' (se añade), 'ico' (se añade si se confirma) y
    'candidate' (solo se apunta). ``flags`` es None si Hunspell no lo conoce.
    """
    if flags is not None:
        if "G" not in flags:
            return None
        fem = feminine_form(word)
        return ("hunspell", fem) if fem else None
    fem = feminine_form(word)
    if fem is None:
        return None
    return ("ico", fem) if is_esdrujula_ico(word) else ("candidate", fem)


def attested(word: str, counts: dict[str, int], zipf_frequency) -> bool:
    if counts.get(word, 0) >= MIN_COUNT:
        return True
    return zipf_frequency is not None and zipf_frequency(word, "es") >= MIN_ZIPF


def rae_client(api_key: str, timeout: float) -> httpx.Client:
    """Cliente para rae-api.com, con la clave si la hay.

    Sin redirecciones: httpx conservaría esta cabecera si saltara a otro dominio.
    """
    headers = {"X-API-Key": api_key} if api_key else None
    return httpx.Client(timeout=timeout, headers=headers, follow_redirects=False)


@dataclass(frozen=True)
class RateLimited:
    """Respuesta de límite de tasa; retry_after en segundos, si la API lo dice."""

    retry_after: float | None


class RaeChecker:
    """Pregunta a rae-api.com si una forma existe, despacio y con caché en disco.

    La caché guarda las respuestas firmes (existe / no existe) y se escribe tras
    cada una, así que cortar el proceso no pierde nada. Los fallos no se
    guardan: se vuelven a intentar en otra ejecución.

    Cuando la API agota la cuota responde con 'retry_after' (segundos hasta que
    vuelve a aceptar consultas, a veces horas): se espera ese tiempo en lugar de
    seguir preguntando, que solo gastaría la palabra.
    """

    def __init__(
        self,
        client: httpx.Client,
        base_url: str,
        cache_path: Path,
        *,
        delay: float,
        sleep: Callable[[float], None] = time.sleep,
        retries: int = 3,
    ) -> None:
        self.client = client
        self.base_url = base_url
        self.cache_path = cache_path
        self.delay = delay
        self.sleep = sleep
        self.retries = retries
        self.cache: dict[str, bool] = {}
        if cache_path.exists():
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
        self._asked = False

    def check(self, word: str) -> bool | None:
        """True si existe, False si no, None si no se pudo saber."""
        if word in self.cache:
            return self.cache[word]
        failures = 0
        waits = 0
        wait = self.delay
        while True:
            # Pausa entre consultas, o la que pidió la API tras el límite de tasa.
            if self._asked:
                self.sleep(wait)
            self._asked = True
            wait = self.delay
            answer = self._ask(word)
            if isinstance(answer, RateLimited):
                waits += 1
                if waits > MAX_RATE_LIMIT_WAITS:
                    return None
                wait = answer.retry_after or self.delay * 5
                if wait > 60:
                    resume = datetime.now() + timedelta(seconds=wait)
                    print(
                        f"  Cuota de la RAE agotada: espero hasta las {resume:%H:%M}.",
                        flush=True,
                    )
                continue
            if answer is None:
                failures += 1
                if failures > self.retries:
                    return None
                continue
            self.cache[word] = answer
            self._save()
            return answer

    def _ask(self, word: str) -> bool | RateLimited | None:
        try:
            response = self.client.get(f"{self.base_url}/{quote(word, safe='')}")
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        if payload.get("ok"):
            return True
        error = payload.get("error")
        if error == "NOT_FOUND":
            return False
        if error == "RATE_LIMIT_EXCEEDED" or response.status_code == 429:
            retry_after = payload.get("retry_after") or response.headers.get("Retry-After")
            try:
                # Un segundo de margen para no llegar justo antes del reinicio.
                return RateLimited(float(retry_after) + 1 if retry_after else None)
            except ValueError:
                return RateLimited(None)
        return None

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0), encoding="utf-8")
        tmp.replace(self.cache_path)


def decide(
    lemmas: list[str],
    existing: set[str],
    dic: dict[str, set[str]],
    counts: dict[str, int],
    zipf_frequency,
    rae: RaeChecker | None,
) -> tuple[dict[str, str], dict[str, str], dict[str, int]]:
    """Decide sin tocar la base. Devuelve (femeninos, candidatos, estadísticas).

    ``femeninos`` y ``candidatos`` van de la forma femenina al lema. ``existing``
    son las formas ya presentes en minúscula: un femenino que ya es lema propio
    ('casa', 'puerta') no se toca.
    """
    feminines: dict[str, str] = {}
    candidates: dict[str, str] = {}
    stats = dict.fromkeys(
        ("hunspell", "ico_corpus", "ico_rae", "ico_rejected", "ico_pending", "candidate"), 0
    )
    ico_queue: list[tuple[str, str]] = []
    for word in lemmas:
        decision = classify(word, dic.get(word))
        if decision is None:
            continue
        way, fem = decision
        if fem.lower() in existing or fem in feminines:
            continue
        if way == "hunspell":
            feminines[fem] = word
            stats["hunspell"] += 1
        elif way == "candidate":
            candidates[fem] = word
            stats["candidate"] += 1
        elif attested(fem, counts, zipf_frequency):
            feminines[fem] = word
            stats["ico_corpus"] += 1
        else:
            ico_queue.append((fem, word))

    pending = [item for item in ico_queue if rae is None or item[0] not in rae.cache]
    if rae is not None and pending:
        print(f"Consultando a la RAE {len(pending)} esdrújulas sin corpus (Ctrl+C para parar).")
    asked = 0
    for fem, word in ico_queue:
        answer = None
        if rae is not None:
            fresh = fem not in rae.cache
            answer = rae.check(fem)
            if fresh:
                asked += 1
                mark = {True: "sí", False: "no", None: "sin respuesta"}[answer]
                print(f"  RAE {asked}/{len(pending)}: {fem} -> {mark}", flush=True)
        if answer is True:
            feminines[fem] = word
            stats["ico_rae"] += 1
        elif answer is False:
            stats["ico_rejected"] += 1
        else:
            candidates[fem] = word
            stats["ico_pending"] += 1
    return feminines, candidates, stats


def apply(conn, feminines: dict[str, str], candidates: dict[str, str], source: str, stats) -> int:
    """Sustituye los femeninos derivados del índice. Devuelve cuántos quedan."""
    conn.execute("DELETE FROM words WHERE is_derived = 1")
    conn.execute("UPDATE words SET feminine_candidate = NULL WHERE feminine_candidate IS NOT NULL")
    conn.executemany(
        "INSERT OR IGNORE INTO words "
        "(word, word_norm, first_letter, letter_count, is_derived, base_word) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        [
            (fem, normalize_word(fem), first_letter(fem), letter_count(fem), base)
            for fem, base in sorted(feminines.items())
        ],
    )
    conn.executemany(
        "UPDATE words SET feminine_candidate = ? WHERE word = ? AND is_derived = 0",
        [(fem, base) for fem, base in candidates.items()],
    )
    conn.executemany(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [
            ("derived_source", source),
            ("derived_feminines", json.dumps(stats)),
            ("derived_updated_at", datetime.now(UTC).isoformat()),
        ],
    )
    return conn.execute("SELECT COUNT(*) FROM words WHERE is_derived = 1").fetchone()[0]


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Añade los femeninos derivados al índice.")
    parser.add_argument("--no-rae", action="store_true", help="No consultar a rae-api.com.")
    parser.add_argument("--local", help="Fichero local de OpenSubtitles ('palabra apariciones').")
    args = parser.parse_args(argv)

    db = Path(settings.database_path)
    if not db.exists():
        print(f"No hay índice en {db}. Ejecuta antes scripts/build_index.py.")
        return 1
    hunspell = Path(settings.hunspell_dir)
    if not (hunspell / "index.dic").exists():
        print(f"No está Hunspell en {hunspell}. Ejecuta antes scripts/fetch_hunspell.py.")
        return 1

    dic = parse_dic((hunspell / "index.dic").read_text(encoding="utf-8"))
    source_file = hunspell / SOURCE_FILE
    source = source_file.read_text(encoding="utf-8").strip() if source_file.exists() else "?"
    print(f"Hunspell: {len(dic):,} entradas ({source}).")

    if args.local:
        text = Path(args.local).read_text(encoding="utf-8")
    else:
        print(f"Descargando lista de frecuencias: {settings.freq_list_url}")
        text = download_list(settings.freq_list_url)
    counts, _ = parse_counts(text)
    zipf_frequency = load_wordfreq()
    if zipf_frequency is None:
        print("AVISO: wordfreq no está instalado; el corpus será solo OpenSubtitles.")

    with get_connection() as conn:
        init_schema(conn)
        rows = conn.execute(
            "SELECT word, is_phrase, is_affix, is_proper FROM words WHERE is_derived = 0"
        ).fetchall()
    existing = {row["word"].lower() for row in rows}
    lemmas = [
        row["word"] for row in rows if not (row["is_phrase"] or row["is_affix"] or row["is_proper"])
    ]

    with rae_client(settings.rae_check_api_key, settings.http_timeout) as client:
        rae = None
        if not args.no_rae:
            rae = RaeChecker(
                client,
                settings.rae_api_base,
                Path(settings.rae_check_cache),
                delay=settings.rae_check_delay,
            )
        feminines, candidates, stats = decide(lemmas, existing, dic, counts, zipf_frequency, rae)

    with get_connection() as conn:
        total = apply(conn, feminines, candidates, source, stats)
    print(
        f"Listo. {total:,} femeninos en el índice: {stats['hunspell']:,} de Hunspell, "
        f"{stats['ico_corpus']:,} esdrújulas confirmadas por corpus y "
        f"{stats['ico_rae']:,} por la RAE ({stats['ico_rejected']:,} rechazadas, "
        f"{stats['ico_pending']:,} pendientes). "
        f"{stats['candidate']:,} femeninos posibles apuntados sin confirmar."
    )
    print("Ejecuta ahora scripts/enrich_frequency.py para darles frecuencia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
