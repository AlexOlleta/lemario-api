"""Consultas de palabras sobre SQLite."""

from __future__ import annotations

from collections.abc import Sequence

from ..database import get_connection
from ..normalize import first_letter, matches_ending, normalize_ending, normalize_word


def _phrase_clause(include_phrases: bool) -> str:
    return "" if include_phrases else " AND is_phrase = 0"


def _affix_clause(include_affixes: bool) -> str:
    """Los afijos ('-algia', 'supra-') no son palabras jugables: fuera por defecto."""
    return "" if include_affixes else " AND is_affix = 0"


def _proper_clause(include_proper: bool) -> str:
    """Los nombres propios ('Madrid') tampoco son palabras de juego."""
    return "" if include_proper else " AND is_proper = 0"


def _derived_clause(include_derived: bool) -> str:
    """Las formas derivadas ('lógica' de 'lógico') no son lemas de la RAE."""
    return "" if include_derived else " AND is_derived = 0"


def _freq_clause(tier: str | None, min_zipf: float | None) -> tuple[str, list[object]]:
    """Filtro opcional por frecuencia. Devuelve (SQL, parámetros).

    'tier' selecciona un nivel exacto; 'min_zipf' pide "esta frecuencia o más".
    Sin ninguno de los dos no se filtra: la frecuencia nunca se impone, porque
    un diccionario también es un caso de uso legítimo.
    """
    sql = ""
    params: list[object] = []
    if tier is not None:
        sql += " AND freq_tier = ?"
        params.append(tier)
    if min_zipf is not None:
        sql += " AND zipf >= ?"
        params.append(min_zipf)
    return sql, params


def words_by_letter(
    letter: str,
    *,
    limit: int,
    offset: int,
    include_phrases: bool,
    include_affixes: bool,
    include_proper: bool,
    include_derived: bool,
    tier: str | None = None,
    min_zipf: float | None = None,
) -> tuple[int, list[str]]:
    """Palabras cuya primera letra (normalizada) coincide. Devuelve (total, página)."""
    key = first_letter(letter)
    freq_sql, freq_params = _freq_clause(tier, min_zipf)
    clause = (
        _phrase_clause(include_phrases)
        + _affix_clause(include_affixes)
        + _proper_clause(include_proper)
        + _derived_clause(include_derived)
        + freq_sql
    )
    with get_connection(read_only=True) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM words WHERE first_letter = ?{clause}",
            (key, *freq_params),
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT word FROM words WHERE first_letter = ?{clause} "
            "ORDER BY word_norm LIMIT ? OFFSET ?",
            (key, *freq_params, limit, offset),
        ).fetchall()
    return total, [r["word"] for r in rows]


def words_by_length(
    length: int,
    *,
    limit: int,
    offset: int,
    include_phrases: bool,
    include_affixes: bool,
    include_proper: bool,
    include_derived: bool,
    tier: str | None = None,
    min_zipf: float | None = None,
) -> tuple[int, list[str]]:
    """Palabras con un número exacto de letras. Devuelve (total, página)."""
    freq_sql, freq_params = _freq_clause(tier, min_zipf)
    clause = (
        _phrase_clause(include_phrases)
        + _affix_clause(include_affixes)
        + _proper_clause(include_proper)
        + _derived_clause(include_derived)
        + freq_sql
    )
    with get_connection(read_only=True) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM words WHERE letter_count = ?{clause}",
            (length, *freq_params),
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT word FROM words WHERE letter_count = ?{clause} "
            "ORDER BY word_norm LIMIT ? OFFSET ?",
            (length, *freq_params, limit, offset),
        ).fetchall()
    return total, [r["word"] for r in rows]


def _like_pattern(q: str, mode: str) -> str:
    """Construye el patrón LIKE escapando los comodines del input del usuario.

    El substring se normaliza igual que las palabras (minúsculas, sin tildes,
    conservando la 'ñ') y se escapan '\\', '%' y '_' para que se traten como
    literales. Se usa junto a ESCAPE '\\' en la consulta.
    """
    norm = normalize_word(q)
    escaped = norm.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    if mode == "prefix":
        return f"{escaped}%"
    if mode == "suffix":
        return f"%{escaped}"
    return f"%{escaped}%"


def words_by_substring(
    q: str,
    *,
    mode: str,
    limit: int,
    offset: int,
    include_phrases: bool,
    include_affixes: bool,
    include_proper: bool,
    include_derived: bool,
    tier: str | None = None,
    min_zipf: float | None = None,
) -> tuple[int, list[str]]:
    """Palabras cuya forma normalizada casa con el substring. Devuelve (total, página).

    ``mode`` puede ser 'contains' (por defecto), 'prefix' o 'suffix'. La búsqueda
    ignora tildes y mayúsculas; la 'ñ' se trata como letra propia.
    """
    pattern = _like_pattern(q, mode)
    freq_sql, freq_params = _freq_clause(tier, min_zipf)
    clause = (
        _phrase_clause(include_phrases)
        + _affix_clause(include_affixes)
        + _proper_clause(include_proper)
        + _derived_clause(include_derived)
        + freq_sql
    )
    with get_connection(read_only=True) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM words WHERE word_norm LIKE ? ESCAPE '\\'{clause}",
            (pattern, *freq_params),
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT word FROM words "
            f"WHERE word_norm LIKE ? ESCAPE '\\'{clause} "
            "ORDER BY word_norm LIMIT ? OFFSET ?",
            (pattern, *freq_params, limit, offset),
        ).fetchall()
    return total, [r["word"] for r in rows]


def words_by_rhyme(
    ending: str,
    *,
    limit: int,
    offset: int,
    include_phrases: bool,
    include_affixes: bool,
    include_proper: bool,
    include_derived: bool,
    tier: str | None = None,
    min_zipf: float | None = None,
) -> tuple[int, list[str]]:
    """Rima consonante con la terminación. Devuelve (total, página).

    ``word_norm LIKE`` descarta casi todo barato; ``matches_ending`` afina con la
    grafía oficial, donde la tilde cuenta.
    """
    end = normalize_ending(ending)
    pattern = _like_pattern(end, "suffix")
    freq_sql, freq_params = _freq_clause(tier, min_zipf)
    clause = (
        _phrase_clause(include_phrases)
        + _affix_clause(include_affixes)
        + _proper_clause(include_proper)
        + _derived_clause(include_derived)
        + freq_sql
    )
    where = f"word_norm LIKE ? ESCAPE '\\' AND rhyme_match(word, ?){clause}"
    params = (pattern, end, *freq_params)
    with get_connection(read_only=True) as conn:
        conn.create_function("rhyme_match", 2, matches_ending, deterministic=True)
        total = conn.execute(f"SELECT COUNT(*) FROM words WHERE {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT word FROM words WHERE {where} ORDER BY word_norm LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
    return total, [r["word"] for r in rows]


def _pattern_to_like(pattern: str) -> str:
    """Traduce un patrón de juego a un patrón LIKE de SQLite.

    Comodines aceptados: ``_`` y ``?`` para *una* letra y ``*`` para *cero o
    más*. El resto de caracteres se normaliza como las palabras (minúsculas,
    sin tildes, conservando la 'ñ'), y '%' y '\\' se escapan para que sean
    literales: así el usuario nunca puede inyectar comodines propios de SQL.
    """
    out: list[str] = []
    for ch in normalize_word(pattern):
        if ch in ("_", "?"):
            out.append("_")
        elif ch == "*":
            out.append("%")
        elif ch in ("%", "\\"):
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def words_by_pattern(
    pattern: str,
    *,
    length: int | None,
    limit: int,
    offset: int,
    include_phrases: bool,
    include_affixes: bool,
    include_proper: bool,
    include_derived: bool,
    tier: str | None = None,
    min_zipf: float | None = None,
) -> tuple[int, list[str]]:
    """Palabras que casan con un patrón con comodines. Devuelve (total, página).

    Un patrón que empieza por comodín obliga a recorrer la tabla entera (son
    decenas de miles de filas: milisegundos). Pasar ``length`` acota la búsqueda
    con ``idx_words_letter_count`` y es la forma barata de estrecharla.
    """
    like = _pattern_to_like(pattern)
    freq_sql, freq_params = _freq_clause(tier, min_zipf)
    clause = (
        _phrase_clause(include_phrases)
        + _affix_clause(include_affixes)
        + _proper_clause(include_proper)
        + _derived_clause(include_derived)
        + freq_sql
    )
    params: list[object] = [like]
    length_clause = ""
    if length is not None:
        length_clause = " AND letter_count = ?"
        params.append(length)
    params.extend(freq_params)

    where = f"WHERE word_norm LIKE ? ESCAPE '\\'{length_clause}{clause}"
    with get_connection(read_only=True) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM words {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT word FROM words {where} ORDER BY word_norm LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
    return total, [r["word"] for r in rows]


def random_word(
    *,
    letter: str | None = None,
    length: int | None = None,
    include_phrases: bool,
    include_affixes: bool,
    include_proper: bool,
    include_derived: bool,
    tier: str | None = None,
    min_zipf: float | None = None,
) -> str | None:
    """Una palabra al azar que cumpla los criterios opcionales."""
    conditions: list[str] = []
    params: list[object] = []
    if letter:
        conditions.append("first_letter = ?")
        params.append(first_letter(letter))
    if length is not None:
        conditions.append("letter_count = ?")
        params.append(length)
    if not include_phrases:
        conditions.append("is_phrase = 0")
    if not include_affixes:
        conditions.append("is_affix = 0")
    if not include_proper:
        conditions.append("is_proper = 0")
    if not include_derived:
        conditions.append("is_derived = 0")
    if tier is not None:
        conditions.append("freq_tier = ?")
        params.append(tier)
    if min_zipf is not None:
        conditions.append("zipf >= ?")
        params.append(min_zipf)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_connection(read_only=True) as conn:
        row = conn.execute(
            f"SELECT word FROM words{where} ORDER BY RANDOM() LIMIT 1",
            params,
        ).fetchone()
    return row["word"] if row else None


def words_details(words: Sequence[str], *, include_derived: bool = True) -> list[dict | None]:
    """Busca varias palabras de una vez. Devuelve una lista alineada con la entrada.

    Cada elemento es ``None`` (no está en el lemario) o un dict con la grafía
    oficial y sus metadatos. La búsqueda ignora tildes, así que 'aguila'
    encuentra 'águila'; cuando varias grafías comparten forma normalizada se
    devuelve la primera por orden alfabético (igual que la consulta unitaria).
    Sin ``include_derived``, las formas derivadas ('lógica') cuentan como ausentes.
    """
    norms = [normalize_word(w) for w in words]
    unique = sorted({n for n in norms if n})
    candidates: dict[str, list[dict]] = {}
    if unique:
        placeholders = ",".join("?" * len(unique))
        with get_connection(read_only=True) as conn:
            rows = conn.execute(
                "SELECT word, word_norm, letter_count, is_phrase, is_affix, is_proper, "
                "is_derived, base_word, zipf, freq_tier FROM words "
                f"WHERE word_norm IN ({placeholders}){_derived_clause(include_derived)} "
                "ORDER BY word",
                unique,
            ).fetchall()
        for row in rows:
            candidates.setdefault(row["word_norm"], []).append(dict(row))
    return [_pick(word, candidates.get(norm)) for word, norm in zip(words, norms, strict=True)]


def _pick(query: str, candidates: list[dict] | None) -> dict | None:
    """Elige entre entradas que comparten forma normalizada.

    Hay 251 pares así en el lemario: unos difieren en la tilde ('adonde' /
    'adónde') y otros en la caja ('chile' el ají / 'Chile' el país). Manda lo
    que escribió quien consulta; si no coincide con ninguna, se prefiere el
    nombre común antes que el propio, porque es la acepción que espera un juego.
    """
    if not candidates:
        return None
    exact = query.strip()
    for candidate in candidates:
        if candidate["word"] == exact:
            return candidate
    for candidate in candidates:
        if not candidate["is_proper"]:
            return candidate
    return candidates[0]


def word_details(word: str) -> dict | None:
    """Datos de una palabra del lemario (grafía oficial, letras, locución)."""
    return words_details([word])[0]


def word_exists(word: str) -> str | None:
    """Devuelve la grafía oficial si la palabra existe (búsqueda sin tildes)."""
    details = word_details(word)
    return details["word"] if details else None


def frequency_info() -> dict[str, str | None]:
    """Qué fuentes de frecuencia se aplicaron al índice, y cuándo.

    Devuelve ``sources`` a None si nunca se ejecutó scripts/enrich_frequency.py:
    con eso la API puede avisar en vez de devolver listas vacías en silencio.
    """
    with get_connection(read_only=True) as conn:
        rows = conn.execute(
            "SELECT key, value FROM meta WHERE key IN ('freq_sources', 'freq_updated_at')"
        ).fetchall()
    data = {row["key"]: row["value"] for row in rows}
    return {
        "sources": data.get("freq_sources"),
        "updated_at": data.get("freq_updated_at"),
    }
