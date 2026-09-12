"""Endpoints de palabras: por letra, longitud, substring, patrón, existencia y azar."""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from ..config import get_settings
from ..database import database_exists
from ..limiter import limiter
from ..models import RandomWord, WordExists, WordExistsList, WordList
from ..security import require_api_key
from ..services import repository

router = APIRouter(
    prefix="/words",
    tags=["words"],
    dependencies=[Depends(require_api_key)],
)


class Tier(str, Enum):
    """Nivel de frecuencia de uso (ver app/frequency.py)."""

    common = "common"
    medium = "medium"
    rare = "rare"
    unknown = "unknown"


class SearchMode(str, Enum):
    """Modo de coincidencia del substring."""

    contains = "contains"
    prefix = "prefix"
    suffix = "suffix"


def _ensure_db() -> None:
    if not database_exists():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Índice no construido. Ejecuta scripts/build_index.py primero.",
        )


def _freq_filter(tier: Tier | None, min_zipf: float | None) -> tuple[str | None, float | None]:
    """Valida el filtro de frecuencia antes de usarlo.

    Sin enriquecer, todas las palabras son 'unknown' con zipf 0: filtrar
    devolvería listas vacías sin explicar por qué. Mejor decirlo.
    """
    if (tier is not None or min_zipf is not None) and (
        repository.frequency_info()["sources"] is None
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El índice no tiene frecuencias. "
            "Ejecuta scripts/enrich_frequency.py para poder filtrar por ellas.",
        )
    return (tier.value if tier is not None else None), min_zipf


@router.get("/by-letter/{letter}", response_model=WordList)
def by_letter(
    request: Request,
    letter: str = Path(..., min_length=1, max_length=1, description="Primera letra."),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_phrases: bool = Query(False, description="Incluir locuciones (con espacios)."),
    include_affixes: bool = Query(
        False, description="Incluir afijos: prefijos y sufijos ('supra-', '-algia')."
    ),
    include_proper: bool = Query(
        False, description="Incluir nombres propios ('Madrid'); las siglas no lo son."
    ),
    tier: Tier | None = Query(
        None, description="Nivel de frecuencia exacto: common, medium, rare o unknown."
    ),
    min_zipf: float | None = Query(
        None, ge=0, le=8, description="Frecuencia Zipf mínima (4 ≈ uso cotidiano)."
    ),
) -> WordList:
    _ensure_db()
    tier_name, min_zipf = _freq_filter(tier, min_zipf)
    total, words = repository.words_by_letter(
        letter,
        limit=limit,
        offset=offset,
        include_phrases=include_phrases,
        include_affixes=include_affixes,
        include_proper=include_proper,
        tier=tier_name,
        min_zipf=min_zipf,
    )
    return WordList(
        criterion=f"letter={letter.lower()}",
        total=total,
        limit=limit,
        offset=offset,
        count=len(words),
        words=words,
    )


@router.get("/by-length/{length}", response_model=WordList)
def by_length(
    request: Request,
    length: int = Path(..., ge=1, le=100, description="Número de letras."),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_phrases: bool = Query(False, description="Incluir locuciones (con espacios)."),
    include_affixes: bool = Query(
        False, description="Incluir afijos: prefijos y sufijos ('supra-', '-algia')."
    ),
    include_proper: bool = Query(
        False, description="Incluir nombres propios ('Madrid'); las siglas no lo son."
    ),
    tier: Tier | None = Query(
        None, description="Nivel de frecuencia exacto: common, medium, rare o unknown."
    ),
    min_zipf: float | None = Query(
        None, ge=0, le=8, description="Frecuencia Zipf mínima (4 ≈ uso cotidiano)."
    ),
) -> WordList:
    _ensure_db()
    tier_name, min_zipf = _freq_filter(tier, min_zipf)
    total, words = repository.words_by_length(
        length,
        limit=limit,
        offset=offset,
        include_phrases=include_phrases,
        include_affixes=include_affixes,
        include_proper=include_proper,
        tier=tier_name,
        min_zipf=min_zipf,
    )
    return WordList(
        criterion=f"length={length}",
        total=total,
        limit=limit,
        offset=offset,
        count=len(words),
        words=words,
    )


@router.get("/search", response_model=WordList)
def search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=80, description="Substring a buscar."),
    mode: SearchMode = Query(
        SearchMode.contains,
        description="Coincidencia: 'contains' (por defecto), 'prefix' o 'suffix'.",
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_phrases: bool = Query(False, description="Incluir locuciones (con espacios)."),
    include_affixes: bool = Query(
        False, description="Incluir afijos: prefijos y sufijos ('supra-', '-algia')."
    ),
    include_proper: bool = Query(
        False, description="Incluir nombres propios ('Madrid'); las siglas no lo son."
    ),
    tier: Tier | None = Query(
        None, description="Nivel de frecuencia exacto: common, medium, rare o unknown."
    ),
    min_zipf: float | None = Query(
        None, ge=0, le=8, description="Frecuencia Zipf mínima (4 ≈ uso cotidiano)."
    ),
) -> WordList:
    _ensure_db()
    tier_name, min_zipf = _freq_filter(tier, min_zipf)
    total, words = repository.words_by_substring(
        q,
        mode=mode.value,
        limit=limit,
        offset=offset,
        include_phrases=include_phrases,
        include_affixes=include_affixes,
        include_proper=include_proper,
        tier=tier_name,
        min_zipf=min_zipf,
    )
    return WordList(
        criterion=f"{mode.value}={q.lower()}",
        total=total,
        limit=limit,
        offset=offset,
        count=len(words),
        words=words,
    )


@router.get("/pattern", response_model=WordList)
def pattern(
    request: Request,
    p: str = Query(
        ...,
        min_length=1,
        max_length=30,
        description="Patrón con comodines: '_' o '?' = una letra, '*' = cero o más.",
    ),
    length: int | None = Query(
        None,
        ge=1,
        le=100,
        description="Filtra además por número de letras (acota la búsqueda).",
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_phrases: bool = Query(False, description="Incluir locuciones (con espacios)."),
    include_affixes: bool = Query(
        False, description="Incluir afijos: prefijos y sufijos ('supra-', '-algia')."
    ),
    include_proper: bool = Query(
        False, description="Incluir nombres propios ('Madrid'); las siglas no lo son."
    ),
    tier: Tier | None = Query(
        None, description="Nivel de frecuencia exacto: common, medium, rare o unknown."
    ),
    min_zipf: float | None = Query(
        None, ge=0, le=8, description="Frecuencia Zipf mínima (4 ≈ uso cotidiano)."
    ),
) -> WordList:
    """Palabras que casan con un patrón, p. ej. 'c_s_' o '*ción'.

    El patrón se compara con la forma normalizada: ignora tildes y mayúsculas,
    y la 'ñ' es letra propia. Los '%' que escriba el cliente son literales.
    """
    _ensure_db()
    tier_name, min_zipf = _freq_filter(tier, min_zipf)
    total, words = repository.words_by_pattern(
        p,
        length=length,
        limit=limit,
        offset=offset,
        include_phrases=include_phrases,
        include_affixes=include_affixes,
        include_proper=include_proper,
        tier=tier_name,
        min_zipf=min_zipf,
    )
    return WordList(
        criterion=f"pattern={p.lower()}",
        total=total,
        limit=limit,
        offset=offset,
        count=len(words),
        words=words,
    )


def _to_exists(query: str, details: dict | None) -> WordExists:
    if details is None:
        return WordExists(query=query, exists=False)
    return WordExists(
        query=query,
        exists=True,
        word=details["word"],
        letter_count=details["letter_count"],
        is_phrase=bool(details["is_phrase"]),
        is_affix=bool(details["is_affix"]),
        is_proper=bool(details["is_proper"]),
        zipf=details["zipf"],
        tier=details["freq_tier"],
    )


@router.get("/exists", response_model=WordExistsList)
@limiter.limit(get_settings().rate_limit_exists)
def exists_batch(
    request: Request,
    w: list[str] = Query(
        ...,
        min_length=1,
        max_length=100,
        description="Palabra a comprobar; repite el parámetro para varias.",
    ),
) -> WordExistsList:
    """Comprueba varias palabras de una vez (una sola consulta a SQLite).

    Pensado para juegos que validan muchos candidatos por jugada (sopa de
    letras, Boggle). Los resultados vuelven en el mismo orden de la consulta.
    """
    _ensure_db()
    if any(len(word) > 80 for word in w):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cada palabra debe tener 80 caracteres o menos.",
        )
    results = [
        _to_exists(word, details)
        for word, details in zip(w, repository.words_details(w), strict=True)
    ]
    return WordExistsList(count=len(results), results=results)


@router.get("/exists/{word}", response_model=WordExists)
@limiter.limit(get_settings().rate_limit_exists)
def exists(
    request: Request,
    word: str = Path(..., min_length=1, max_length=80, description="Palabra a comprobar."),
) -> WordExists:
    """¿Está la palabra en el lemario? Responde 200 tanto si sí como si no.

    Es una pregunta, no un recurso: un 404 obligaría a los clientes a tratar
    "no existe" como un error. La búsqueda ignora tildes ('aguila' encuentra
    'águila') y devuelve la grafía oficial para que el juego decida si la
    acepta tal cual. No sale a la red.
    """
    _ensure_db()
    return _to_exists(word, repository.word_details(word))


@router.get("/random", response_model=RandomWord)
def random(
    request: Request,
    letter: str | None = Query(None, min_length=1, max_length=1),
    length: int | None = Query(None, ge=1, le=100),
    include_phrases: bool = Query(False),
    include_affixes: bool = Query(
        False, description="Incluir afijos: prefijos y sufijos ('supra-', '-algia')."
    ),
    include_proper: bool = Query(
        False, description="Incluir nombres propios ('Madrid'); las siglas no lo son."
    ),
    tier: Tier | None = Query(
        None, description="Nivel de frecuencia exacto: common, medium, rare o unknown."
    ),
    min_zipf: float | None = Query(
        None, ge=0, le=8, description="Frecuencia Zipf mínima (4 ≈ uso cotidiano)."
    ),
) -> RandomWord:
    _ensure_db()
    tier_name, min_zipf = _freq_filter(tier, min_zipf)
    word = repository.random_word(
        letter=letter,
        length=length,
        include_phrases=include_phrases,
        include_affixes=include_affixes,
        include_proper=include_proper,
        tier=tier_name,
        min_zipf=min_zipf,
    )
    if word is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay palabras que cumplan los criterios.",
        )
    return RandomWord(word=word)
