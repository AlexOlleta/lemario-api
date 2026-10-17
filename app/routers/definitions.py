"""Endpoint de definiciones."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from ..config import get_settings
from ..database import database_exists
from ..limiter import limiter
from ..models import Definition
from ..security import require_api_key
from ..services import repository
from ..services.definitions import (
    SourceUnavailable,
    WordNotFound,
    get_definition,
)

router = APIRouter(
    prefix="/definitions",
    tags=["definitions"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/{word}", response_model=Definition)
@limiter.limit(get_settings().rate_limit_definitions)
async def definition(
    request: Request,
    word: str = Path(..., min_length=1, max_length=80),
    force: bool = Query(False, description="Forzar nueva consulta ignorando la caché."),
    require_in_list: bool = Query(
        True,
        description="Exigir que la palabra esté en el lemario RAE antes de consultar.",
    ),
) -> Definition:
    if require_in_list and database_exists():
        official = repository.word_exists(word)
        if official is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{word}' no está en el lemario RAE. "
                "Usa require_in_list=false para consultarla igualmente.",
            )
        word = official

    try:
        return await get_definition(word, force=force)
    except WordNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró definición para '{word}'.",
        ) from None
    except SourceUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Fuentes de definiciones no disponibles: {exc}",
        ) from exc
