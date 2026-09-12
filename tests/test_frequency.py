"""Pruebas de las reglas de frecuencia (escala Zipf y niveles)."""

from __future__ import annotations

import pytest

from app.frequency import count_to_zipf, tier_for

CORPUS = 423_290_924  # tamaño del corpus de OpenSubtitles 2018


@pytest.mark.parametrize(
    "count,expected",
    [
        (14_459_520, 7.53),  # 'de', la palabra más frecuente
        (1_000, 3.37),
        (1, 0.37),           # una sola aparición sigue siendo un dato
        (0, 0.0),            # sin datos
    ],
)
def test_count_to_zipf(count, expected):
    assert count_to_zipf(count, CORPUS) == expected


def test_count_to_zipf_never_returns_zero_for_a_real_count():
    # 0.0 significa "sin datos", así que una aparición real no puede valer 0
    # ni aunque el corpus sea gigantesco.
    assert count_to_zipf(1, 10**15) > 0


def test_count_to_zipf_guards_against_empty_corpus():
    assert count_to_zipf(10, 0) == 0.0


@pytest.mark.parametrize(
    "zipf,expected",
    [
        (5.77, "common"),
        (4.0, "common"),    # frontera inferior de 'common'
        (3.99, "medium"),
        (3.0, "medium"),    # frontera inferior de 'medium'
        (2.99, "rare"),
        (0.01, "rare"),
        (0.0, "unknown"),   # 'unknown' no es "rarísima": es "no sabemos"
    ],
)
def test_tier_for(zipf, expected):
    assert tier_for(zipf) == expected
