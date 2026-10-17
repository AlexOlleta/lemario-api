"""Pruebas de la rima consonante: tilde estricta y monosílabos."""

from __future__ import annotations

import pytest

from app.database import get_connection
from app.normalize import (
    first_letter,
    is_affix,
    is_monosyllable,
    is_phrase,
    is_proper,
    letter_count,
    matches_ending,
    normalize_ending,
    normalize_word,
)

RHYME_WORDS = [
    "hijo", "prolijo", "canto", "santo", "cantó", "canción", "corazón",
    "son", "pon", "bien", "tío", "mío", "dio", "farol", "árbol", "buen son",
    "Sión",
]  # fmt: skip


@pytest.fixture(autouse=True)
def rhyme_words():
    """Inserta palabras de rima solo mientras dura la prueba (no altera otros conteos)."""
    rows = [
        (w, normalize_word(w), first_letter(w), letter_count(w),
         int(is_phrase(w)), int(is_affix(w)), int(is_proper(w)))
        for w in RHYME_WORDS
    ]  # fmt: skip
    with get_connection() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO words (word, word_norm, first_letter, letter_count, "
            "is_phrase, is_affix, is_proper) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    yield
    with get_connection() as conn:
        conn.executemany("DELETE FROM words WHERE word = ?", [(w,) for w in RHYME_WORDS])


def _rhymes(client, auth, ending, **params):
    r = client.get("/words/rhymes", params={"ending": ending, **params}, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize(
    "word,expected",
    [
        ("son", True), ("pan", True), ("bien", True), ("guion", True), ("rio", True),
        ("hoy", True), ("buey", True), ("y", True), ("ruin", True), ("buen son", True),
        ("tío", False), ("río", False), ("aire", False), ("casa", False),
        ("leo", False), ("búho", False), ("a priori", False),
    ],
)  # fmt: skip
def test_is_monosyllable(word, expected):
    assert is_monosyllable(word) is expected


def test_matches_ending_is_literal_and_accent_strict():
    assert matches_ending("canto", "anto")
    assert not matches_ending("cantó", "anto")
    assert matches_ending("cantó", "ó")
    assert matches_ending("CANCIÓN", normalize_ending("ón"))


def test_matches_ending_adds_monosyllables_only_with_accent():
    assert matches_ending("son", "ón")
    assert matches_ending("son", "on")  # sin tilde también es literal
    assert not matches_ending("canción", "on")  # y 'ón' no es 'on'
    assert not matches_ending("casa", "ása")  # llana: no es monosílabo
    assert not matches_ending("dio", "ío")


def test_rhyme_without_accent_is_literal(client, auth):
    body = _rhymes(client, auth, "ijo")
    assert set(body["words"]) == {"hijo", "prolijo"}
    assert body["criterion"] == "rhyme=ijo"


def test_rhyme_separates_canto_from_canto_accented(client, auth):
    assert set(_rhymes(client, auth, "anto")["words"]) == {"canto", "santo"}
    # 'ó' literal: 'cantó' y el monosílabo 'dio' (acaba en 'o'); no 'canto'.
    assert set(_rhymes(client, auth, "ó")["words"]) == {"cantó", "dio"}


def test_rhyme_with_accent_adds_monosyllables(client, auth):
    words = set(_rhymes(client, auth, "ón")["words"])
    assert words == {"canción", "corazón", "son", "pon"}  # 'bien' no acaba en 'on'


def test_rhyme_hiatus_excludes_diphthong_monosyllable(client, auth):
    assert set(_rhymes(client, auth, "ío")["words"]) == {"tío", "mío"}


def test_rhyme_ignores_case_in_ending(client, auth):
    assert set(_rhymes(client, auth, "ÓN")["words"]) == set(_rhymes(client, auth, "ón")["words"])


def test_rhyme_phrases_and_proper_are_opt_in(client, auth):
    assert "buen son" not in _rhymes(client, auth, "ón")["words"]
    assert "buen son" in _rhymes(client, auth, "ón", include_phrases="true")["words"]
    assert "Sión" not in _rhymes(client, auth, "ón")["words"]
    assert "Sión" in _rhymes(client, auth, "ón", include_proper="true")["words"]


def test_rhyme_pagination(client, auth):
    p1 = _rhymes(client, auth, "ón", limit=2, offset=0)
    p2 = _rhymes(client, auth, "ón", limit=2, offset=2)
    assert p1["total"] == p2["total"] == 4
    assert p1["count"] == p2["count"] == 2
    assert set(p1["words"]).isdisjoint(p2["words"])


def test_rhyme_frequency_filter_does_not_break_total(client, auth):
    # Ninguna palabra de prueba es 'common': debe responder 0, no fallar.
    body = _rhymes(client, auth, "ijo", tier="common")
    assert body["total"] == 0
    assert body["words"] == []


@pytest.mark.parametrize("ending", ["a_b", "%", "a b", "ij0", "-ijo"])
def test_rhyme_rejects_non_letters(client, auth, ending):
    r = client.get("/words/rhymes", params={"ending": ending}, headers=auth)
    assert r.status_code == 422


def test_rhyme_requires_ending_and_api_key(client, auth):
    assert client.get("/words/rhymes", headers=auth).status_code == 422
    assert client.get("/words/rhymes?ending=ijo").status_code == 401
