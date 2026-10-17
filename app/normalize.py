"""Normalización de palabras en español.

Las tildes se eliminan para buscar y agrupar ('á' -> 'a'), la 'ñ' es una letra
propia y la longitud cuenta letras (se ignoran espacios y guiones).
"""

from __future__ import annotations

import re
import unicodedata

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


_VOWELS = set("aeiouáéíóúü")
_ACCENTED = set("áéíóú")
_WEAK = set("iuü")  # vocales débiles sin tilde ('y' final se trata aparte)


def normalize_ending(text: str) -> str:
    """Forma de una terminación de rima: minúsculas y NFC, **conservando** las tildes."""
    return unicodedata.normalize("NFC", text.strip()).lower()


def _joins(prev: str, cur: str) -> bool:
    """Diptongo: al menos una débil sin tilde. Dos abiertas ('eo') o 'río' no lo forman."""
    return prev in _WEAK or cur in _WEAK


def is_monosyllable(text: str) -> bool:
    """Una sola sílaba (en una locución, la última palabra), contando núcleos vocálicos.

    Sigue el criterio ortográfico de la RAE: 'guion', 'rio' y 'fie' son monosílabos.
    La 'y' es vocal solo al final ('hoy', 'ley').
    """
    word = re.split(r"[\s-]+", normalize_ending(text))[-1]
    letters = [c for c in word if c.isalpha()]
    nuclei = 0
    prev: str | None = None
    for i, ch in enumerate(letters):
        if ch == "y" and i == len(letters) - 1:
            ch = "i"
        if ch not in _VOWELS:
            prev = None
            continue
        if prev is None or not _joins(prev, ch):
            nuclei += 1
        prev = ch
    return nuclei == 1


def matches_ending(word: str, ending: str) -> bool:
    """Rima consonante: coincidencia literal, con la tilde estricta ('canto' no es 'cantó').

    Si ``ending`` lleva tilde también valen los monosílabos, que no la llevan
    ('son' rima con 'canción'), salvo si tras la vocal tildada hay otra vocal:
    'ío' (tío) no admite 'dio'. ``ending`` llega ya normalizado.
    """
    norm = normalize_ending(word)
    if norm.endswith(ending):
        return True
    last = max((i for i, c in enumerate(ending) if c in _ACCENTED), default=-1)
    if last < 0 or any(c in _VOWELS for c in ending[last + 1 :]):
        return False
    return strip_accents(norm).endswith(strip_accents(ending)) and is_monosyllable(norm)


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
