"""Normalización de palabras en español.

Reglas (acordadas con el usuario):
- Las tildes se eliminan para buscar/agrupar: 'á' -> 'a'.
- La 'ñ' es una letra propia y se conserva.
- La longitud se mide en número de letras (se ignoran espacios y guiones).
"""

from __future__ import annotations

import unicodedata

# Caracteres que conservamos sin descomponer.
_KEEP = {"ñ", "Ñ"}


def strip_accents(text: str) -> str:
    """Elimina tildes manteniendo la 'ñ'."""
    out: list[str] = []
    for ch in text:
        if ch in _KEEP:
            out.append(ch)
            continue
        decomposed = unicodedata.normalize("NFD", ch)
        out.append("".join(c for c in decomposed if unicodedata.category(c) != "Mn"))
    return unicodedata.normalize("NFC", "".join(out))


def normalize_word(text: str) -> str:
    """Forma normalizada para búsqueda: minúsculas, sin tildes, con 'ñ'."""
    return strip_accents(text.strip()).lower()


def first_letter(text: str) -> str:
    """Primera letra normalizada de la palabra ('á...' -> 'a', 'ñ...' -> 'ñ')."""
    norm = normalize_word(text)
    return norm[0] if norm else ""


def letter_count(text: str) -> int:
    """Número de letras (ignora espacios, guiones y signos)."""
    return sum(1 for c in text if c.isalpha())


def is_phrase(text: str) -> bool:
    """True si la entrada es una locución (contiene espacios)."""
    return " " in text.strip()


def is_affix(text: str) -> bool:
    """True si la entrada es un afijo del lemario: prefijo o sufijo.

    El lemario incluye elementos compositivos que no son palabras por sí solos:
    prefijos con guion final ('supra-', 'hetero-') y sufijos con guion inicial
    ('-algia', '-logía'). El guion **interior** no cuenta: 'ping-pong' y
    'espacio-tiempo' son palabras compuestas legítimas.
    """
    stripped = text.strip()
    return stripped.startswith("-") or stripped.endswith("-")


def is_proper(text: str) -> bool:
    """True si la entrada es un nombre propio, según cómo la escribe la RAE.

    El criterio es la grafía oficial del lemario, no la frecuencia: 'Chile'
    (el país) y 'chile' (el ají) son dos entradas distintas, y 'mateo' —que en
    Chile es quien estudia mucho— es un nombre común aunque exista 'Mateo'.

    Las siglas ('ADN', 'CD-ROM') van en mayúsculas pero **no** son nombres
    propios, así que quedan fuera de esta regla.
    """
    stripped = text.strip()
    if not stripped or stripped == stripped.upper():
        return False
    return stripped[:1].isupper()
