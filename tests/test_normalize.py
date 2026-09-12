"""Pruebas unitarias de normalización (acentos y ñ son liosos en español)."""

from __future__ import annotations

import pytest

from app.normalize import (
    first_letter,
    is_affix,
    is_phrase,
    is_proper,
    letter_count,
    normalize_word,
    strip_accents,
)


@pytest.mark.parametrize(
    "word,expected",
    [
        ("águila", "a"),   # tilde inicial -> letra base
        ("Árbol", "a"),    # mayúscula con tilde
        ("éxito", "e"),
        ("ñandú", "ñ"),    # la ñ es letra propia, no se convierte en 'n'
        ("Ñoño", "ñ"),
        ("zaherir", "z"),
    ],
)
def test_first_letter(word, expected):
    assert first_letter(word) == expected


def test_enye_is_distinct_from_n():
    # 'año' y 'ano' NO deben colapsar a la misma forma normalizada.
    assert normalize_word("año") == "año"
    assert normalize_word("ano") == "ano"
    assert normalize_word("año") != normalize_word("ano")


def test_accent_insensitive_search():
    # Buscar sin tilde debe llevar a la misma forma normalizada.
    assert normalize_word("café") == normalize_word("cafe") == "cafe"
    assert normalize_word("ÁGUILA") == "aguila"


def test_strip_accents_keeps_enye():
    assert strip_accents("ñoñería") == "ñoñeria"
    assert strip_accents("pingüino") == "pinguino"  # diéresis fuera, sin ñ


@pytest.mark.parametrize(
    "word,expected",
    [
        ("café", 4),
        ("ñandú", 5),
        ("ñoñería", 7),     # ñ-o-ñ-e-r-í-a
        ("a priori", 7),    # ignora el espacio
        ("-algia", 5),      # ignora el guion
    ],
)
def test_letter_count(word, expected):
    assert letter_count(word) == expected


def test_is_phrase():
    assert is_phrase("a priori") is True
    assert is_phrase("casa") is False


@pytest.mark.parametrize(
    "word,expected",
    [
        ("-algia", True),           # sufijo: guion inicial
        ("-logía", True),
        ("supra-", True),           # prefijo: guion final
        ("hetero-", True),
        ("ping-pong", False),       # guion interior: palabra compuesta
        ("espacio-tiempo", False),
        ("casa", False),
    ],
)
def test_is_affix(word, expected):
    assert is_affix(word) is expected


@pytest.mark.parametrize(
    "word,expected",
    [
        ("Madrid", True),
        ("Alzheimer", True),
        ("Chile", True),      # el país
        ("chile", False),     # el ají: el lemario tiene las dos entradas
        ("mateo", False),     # nombre común en Chile, aunque exista 'Mateo'
        ("ADN", False),       # sigla, no nombre propio
        ("CD-ROM", False),
        ("casa", False),
    ],
)
def test_is_proper(word, expected):
    assert is_proper(word) is expected
