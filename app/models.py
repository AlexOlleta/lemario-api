"""Modelos de respuesta (Pydantic)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WordList(BaseModel):
    """Lista paginada de palabras que cumplen un criterio."""

    criterion: str = Field(..., description="Criterio aplicado, p. ej. 'letter=a'.")
    total: int = Field(..., description="Total de palabras que cumplen el criterio.")
    limit: int
    offset: int
    count: int = Field(..., description="Número de palabras en esta página.")
    words: list[str]


class RandomWord(BaseModel):
    word: str


class WordExists(BaseModel):
    """Resultado de comprobar si una palabra está en el lemario."""

    query: str = Field(..., description="La palabra tal y como se consultó.")
    exists: bool
    word: str | None = Field(
        None,
        description="Grafía oficial (con tildes) si existe; null si no.",
    )
    letter_count: int | None = Field(None, description="Número de letras, si existe.")
    is_phrase: bool | None = Field(None, description="True si es una locución.")
    is_affix: bool | None = Field(
        None, description="True si es un afijo: prefijo ('supra-') o sufijo ('-algia')."
    )
    is_proper: bool | None = Field(
        None, description="True si es un nombre propio ('Madrid'); las siglas no."
    )
    is_derived: bool | None = Field(
        None, description="True si es una forma derivada, no un lema de la RAE ('lógica')."
    )
    base_word: str | None = Field(
        None, description="Lema del que deriva la forma ('lógico'); null si es un lema."
    )
    zipf: float | None = Field(None, description="Frecuencia en escala Zipf; 0 si no hay datos.")
    tier: str | None = Field(None, description="Nivel: 'common', 'medium', 'rare' o 'unknown'.")


class WordExistsList(BaseModel):
    """Resultado de una comprobación en lote, en el mismo orden de la consulta."""

    count: int
    results: list[WordExists]


class Sense(BaseModel):
    """Una acepción de la definición."""

    number: str | None = None
    category: str | None = Field(None, description="Categoría gramatical, si está disponible.")
    description: str


class Definition(BaseModel):
    word: str
    source: str = Field(..., description="'rae-api', 'dle.rae.es' o 'cache'.")
    cached: bool = Field(..., description="True si se sirvió desde la caché local.")
    senses: list[Sense]
    fetched_at: datetime


class ErrorResponse(BaseModel):
    detail: str
