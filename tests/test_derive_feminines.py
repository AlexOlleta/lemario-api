"""Pruebas de los femeninos derivados: reglas, decisión, RAE y API."""

from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from app.database import get_connection, init_schema
from app.normalize import first_letter, letter_count, normalize_word
from scripts.derive_feminines import (
    RaeChecker,
    apply,
    classify,
    decide,
    feminine_form,
    is_esdrujula_ico,
    parse_dic,
    rae_client,
)

DIC = """6
lógico/SGk
bonito/GS
bonito/S
pórtico/S
profesor/GS
presidente/GS
"""


def test_parse_dic_merges_repeated_entries():
    flags = parse_dic(DIC)
    assert flags["bonito"] == {"G", "S"}
    assert flags["pórtico"] == {"S"}
    assert len(flags) == 5


@pytest.mark.parametrize(
    ("masculine", "feminine"),
    [
        ("lógico", "lógica"),
        ("profesor", "profesora"),
        ("llorón", "llorona"),  # la tilde se pierde al pasar a llana
        ("holgazán", "holgazana"),
        ("pequeñín", "pequeñina"),
        ("francés", "francesa"),
        ("español", "española"),
        ("presidente", None),  # '-e' > '-a' fuera: daría 'transparenta'
        ("feliz", "feliza"),  # la regla existe; decide la marca G de Hunspell
    ],
)
def test_feminine_form(masculine, feminine):
    assert feminine_form(masculine) == feminine


def test_esdrujula_ico():
    assert is_esdrujula_ico("tautológico")
    assert is_esdrujula_ico("químico")
    assert not is_esdrujula_ico("abanico")  # llana: no lleva tilde
    assert not is_esdrujula_ico("lógica")


def test_classify_trusts_hunspell_when_it_knows_the_word():
    flags = parse_dic(DIC)
    assert classify("lógico", flags["lógico"]) == ("hunspell", "lógica")
    assert classify("pórtico", flags["pórtico"]) is None  # sin marca G
    assert classify("presidente", flags["presidente"]) is None  # regla '-e' excluida


def test_classify_unknown_words():
    assert classify("tautológico", None) == ("ico", "tautológica")
    assert classify("cortapegador", None) == ("candidate", "cortapegadora")
    assert classify("ágape", None) is None


class FakeRae:
    """Sustituto de RaeChecker: respuestas fijas, sin red."""

    def __init__(self, answers):
        self.answers = answers
        self.cache: dict[str, bool] = {}
        self.asked: list[str] = []

    def check(self, word):
        self.asked.append(word)
        return self.answers.get(word)


def test_decide_routes_each_word():
    lemmas = ["lógico", "pórtico", "tautológico", "nigromántico", "telúrico", "griposo", "casa"]
    existing = {w.lower() for w in lemmas} | {"lógica"}
    dic = parse_dic(DIC)
    counts = {"nigromántica": 7}
    rae = FakeRae({"tautológica": True, "telúrica": False})
    feminines, candidates, stats = decide(lemmas, existing - {"lógica"}, dic, counts, None, rae)

    assert feminines == {
        "lógica": "lógico",  # Hunspell
        "nigromántica": "nigromántico",  # corpus
        "tautológica": "tautológico",  # RAE
    }
    assert "telúrica" not in feminines and "telúrica" not in candidates  # RAE dijo que no
    assert candidates == {"griposa": "griposo"}  # sin Hunspell ni regla -ico: solo se apunta
    assert rae.asked == ["tautológica", "telúrica"]  # el corpus ahorra la consulta
    assert stats["hunspell"] == 1 and stats["ico_corpus"] == 1 and stats["ico_rae"] == 1
    assert stats["ico_rejected"] == 1 and stats["candidate"] == 1


def test_decide_skips_feminines_that_are_already_lemmas():
    feminines, _, _ = decide(["lógico"], {"lógico", "lógica"}, parse_dic(DIC), {}, None, None)
    assert feminines == {}


def test_decide_without_rae_leaves_ico_as_candidates():
    feminines, candidates, stats = decide(["tautológico"], set(), {}, {}, None, None)
    assert feminines == {}
    assert candidates == {"tautológica": "tautológico"}
    assert stats["ico_pending"] == 1


def _rae(handler, tmp_path, **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return RaeChecker(
        client, "https://rae.test/api/words", tmp_path / "checks.json", delay=6, **kwargs
    )


def test_rae_client_sends_the_key_only_if_there_is_one():
    with rae_client("clave", 5) as client:
        assert client.headers["X-API-Key"] == "clave"
        assert client.follow_redirects is False
    with rae_client("", 5) as client:
        assert "X-API-Key" not in client.headers


def test_rae_checker_answers_and_caches(tmp_path):
    seen = []

    def handler(request):
        word = request.url.path.rsplit("/", 1)[-1]
        seen.append(word)
        if "t%C3%A9cnica" in str(request.url):
            return httpx.Response(200, json={"ok": True, "data": {"word": "técnica"}})
        return httpx.Response(404, json={"ok": False, "error": "NOT_FOUND"})

    sleeps = []
    rae = _rae(handler, tmp_path, sleep=sleeps.append)
    assert rae.check("técnica") is True
    assert rae.check("pórtica") is False
    assert rae.check("técnica") is True  # de la caché: no vuelve a preguntar
    assert len(seen) == 2
    assert sleeps == [6]  # pausa entre consultas, no antes de la primera
    saved = json.loads((tmp_path / "checks.json").read_text(encoding="utf-8"))
    assert saved == {"técnica": True, "pórtica": False}

    # Una ejecución nueva retoma la caché sin red.
    again = _rae(lambda r: pytest.fail("no debería consultar"), tmp_path)
    assert again.check("pórtica") is False


def test_rae_checker_waits_on_rate_limit_and_retries(tmp_path):
    responses = iter(
        [
            httpx.Response(429, json={"ok": False, "error": "RATE_LIMIT_EXCEEDED"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sleeps = []
    rae = _rae(lambda r: next(responses), tmp_path, sleep=sleeps.append)
    assert rae.check("urémica") is True
    assert sleeps == [30]  # espera larga tras el límite de tasa


def test_rae_checker_waits_what_the_api_asks(tmp_path, capsys):
    responses = iter(
        [
            httpx.Response(
                429, json={"ok": False, "error": "RATE_LIMIT_EXCEEDED", "retry_after": 10636}
            ),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sleeps = []
    rae = _rae(lambda r: next(responses), tmp_path, sleep=sleeps.append)
    assert rae.check("urémica") is True
    assert sleeps == [10637]  # lo que pidió la API, más un segundo de margen
    assert "Cuota de la RAE agotada" in capsys.readouterr().out


def test_rae_checker_gives_up_after_too_many_rate_limits(tmp_path):
    def handler(request):
        return httpx.Response(429, json={"ok": False, "error": "RATE_LIMIT_EXCEEDED"})

    rae = _rae(handler, tmp_path, sleep=lambda s: None)
    assert rae.check("urémica") is None
    assert not (tmp_path / "checks.json").exists()


def test_rae_checker_does_not_cache_failures(tmp_path):
    def handler(request):
        raise httpx.ConnectError("sin red")

    rae = _rae(handler, tmp_path, sleep=lambda s: None, retries=1)
    assert rae.check("urémica") is None
    assert not (tmp_path / "checks.json").exists()


def _memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    conn.executemany(
        "INSERT INTO words (word, word_norm, first_letter, letter_count) VALUES (?, ?, ?, ?)",
        [(w, normalize_word(w), first_letter(w), letter_count(w)) for w in ("lógico", "griposo")],
    )
    return conn


def test_apply_replaces_previous_run():
    conn = _memory_db()
    apply(conn, {"lógica": "lógico", "vieja": "viejo"}, {}, "test@1", {})
    total = apply(conn, {"lógica": "lógico"}, {"griposa": "griposo"}, "test@2", {"hunspell": 1})
    assert total == 1
    row = conn.execute("SELECT * FROM words WHERE word = 'lógica'").fetchone()
    assert row["is_derived"] == 1 and row["base_word"] == "lógico"
    assert row["word_norm"] == "logica" and row["first_letter"] == "l"
    assert conn.execute("SELECT 1 FROM words WHERE word = 'vieja'").fetchone() is None
    candidate = conn.execute("SELECT feminine_candidate FROM words WHERE word = 'griposo'")
    assert candidate.fetchone()[0] == "griposa"
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    assert meta["derived_source"] == "test@2"
    assert json.loads(meta["derived_feminines"]) == {"hunspell": 1}


@pytest.fixture
def derived_perra():
    """Añade 'perra' (de 'perro') como forma derivada mientras dura la prueba."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO words (word, word_norm, first_letter, letter_count, is_derived, "
            "base_word) VALUES ('perra', 'perra', 'p', 5, 1, 'perro')"
        )
    yield
    with get_connection() as conn:
        conn.execute("DELETE FROM words WHERE word = 'perra'")


def test_exists_reports_derived_forms(derived_perra, client, auth):
    body = client.get("/words/exists/perra", headers=auth).json()
    assert body["exists"] is True
    assert body["is_derived"] is True and body["base_word"] == "perro"
    strict = client.get("/words/exists/perra?include_derived=false", headers=auth).json()
    assert strict["exists"] is False
    batch = client.get("/words/exists?w=perra&w=perro&include_derived=false", headers=auth)
    assert [r["exists"] for r in batch.json()["results"]] == [False, True]


@pytest.mark.parametrize(
    "path",
    [
        "/words/by-letter/p",
        "/words/by-length/5",
        "/words/search?q=perr",
        "/words/pattern?p=perr_",
        "/words/rhymes?ending=erra",
    ],
)
def test_listings_include_derived_by_default(derived_perra, client, auth, path):
    assert "perra" in client.get(path, headers=auth).json()["words"]
    sep = "&" if "?" in path else "?"
    strict = client.get(f"{path}{sep}include_derived=false", headers=auth).json()
    assert "perra" not in strict["words"]


def test_random_can_exclude_derived(derived_perra, client, auth):
    query = "/words/random?length=5&letter=p"
    seen = {client.get(query, headers=auth).json()["word"] for _ in range(30)}
    assert seen == {"perro", "perra"}
    strict = {
        client.get(f"{query}&include_derived=false", headers=auth).json()["word"] for _ in range(10)
    }
    assert strict == {"perro"}


def test_definition_of_a_derived_form(derived_perra, client, auth, monkeypatch):
    from app.models import Sense
    from app.services import definitions

    asked = []

    async def fake_rae(_client, word):
        # rae-api resuelve 'perra' a la entrada 'perro, rra'.
        asked.append(word)
        return [Sense(number="1", category="noun", description="Mamífero doméstico")]

    monkeypatch.setattr(definitions, "_fetch_rae_api", fake_rae)
    r = client.get("/definitions/perra", headers=auth)
    assert r.status_code == 200
    assert r.json()["word"] == "perra"
    assert asked == ["perra"]


def test_enrich_skips_crea_for_derived_forms(monkeypatch):
    from contextlib import contextmanager

    from scripts import enrich_frequency

    conn = _memory_db()
    apply(conn, {"lógica": "lógico"}, {}, "test", {})

    @contextmanager
    def memory_connection():
        yield conn

    monkeypatch.setattr(enrich_frequency, "get_connection", memory_connection)
    monkeypatch.setattr(enrich_frequency, "load_wordfreq", lambda: lambda w, lang: 4.0)
    # CREA trae 'lógica' con una entrada residual: el uso real está en 'lógico'.
    enrich_frequency.enrich({"lógico": 100.0, "lógica": 0.5}, {}, 0, use_wordfreq=True)
    sources = dict(conn.execute("SELECT word, freq_source FROM words").fetchall())
    assert sources["lógico"] == "crea"
    assert sources["lógica"] == "wordfreq"
