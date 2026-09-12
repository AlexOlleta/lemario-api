"""Pruebas de los endpoints de palabras (incluye casos con ñ y tildes)."""

from __future__ import annotations


def test_requires_api_key(client):
    # Sin cabecera de API key debe rechazar (401).
    assert client.get("/words/by-letter/a").status_code == 401


def test_by_letter_enye(client, auth):
    r = client.get("/words/by-letter/ñ", headers=auth)
    assert r.status_code == 200
    body = r.json()
    # ñandú, ñoño, ñoñería -> 3; 'ano'/'año' NO deben aparecer aquí.
    assert body["total"] == 3
    assert set(body["words"]) == {"ñandú", "ñoño", "ñoñería"}


def test_by_letter_groups_accent_under_base(client, auth):
    # 'águila' (empieza por 'á') debe aparecer bajo la letra 'a'.
    r = client.get("/words/by-letter/a?include_phrases=false", headers=auth)
    body = r.json()
    assert "águila" in body["words"]
    # 'año' y 'ano' bajo 'a'; la locución 'a priori' excluida por defecto.
    assert body["total"] == 3
    assert "a priori" not in body["words"]


def test_by_letter_accented_path_param(client, auth):
    # Pedir por 'á' debe equivaler a pedir por 'a'.
    r = client.get("/words/by-letter/á", headers=auth)
    assert r.status_code == 200
    assert "águila" in r.json()["words"]


def test_by_letter_include_phrases(client, auth):
    r = client.get("/words/by-letter/a?include_phrases=true", headers=auth)
    assert r.json()["total"] == 4  # incluye 'a priori'


def test_by_length_counts_letters(client, auth):
    # Longitud 4 (sin locuciones): café, casa, ñoño.
    r = client.get("/words/by-length/4", headers=auth)
    body = r.json()
    assert body["total"] == 3
    assert set(body["words"]) == {"café", "casa", "ñoño"}


def test_by_length_distinguishes_enye(client, auth):
    # Longitud 3: 'ano' y 'año' son dos palabras distintas.
    r = client.get("/words/by-length/3", headers=auth)
    body = r.json()
    assert body["total"] == 2
    assert set(body["words"]) == {"ano", "año"}


def test_pagination(client, auth):
    r1 = client.get("/words/by-letter/a?limit=1&offset=0", headers=auth)
    r2 = client.get("/words/by-letter/a?limit=1&offset=1", headers=auth)
    assert r1.json()["count"] == 1
    assert r1.json()["words"] != r2.json()["words"]
    assert r1.json()["total"] == r2.json()["total"] == 3


def test_search_contains_ignores_accents(client, auth):
    # 'oñ' (contains) debe encontrar 'ñoño' y 'ñoñería'; la búsqueda ignora
    # tildes pero la ñ es letra propia.
    r = client.get("/words/search?q=oñ", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert set(body["words"]) == {"ñoño", "ñoñería"}
    assert body["criterion"] == "contains=oñ"


def test_search_contains_normalizes_query(client, auth):
    # Buscar con tilde y mayúscula ('CAFÉ' -> 'cafe') debe casar con 'café'.
    r = client.get("/words/search?q=AFÉ", headers=auth)
    assert set(r.json()["words"]) == {"café"}


def test_search_prefix_mode(client, auth):
    r = client.get("/words/search?q=ca&mode=prefix", headers=auth)
    body = r.json()
    assert set(body["words"]) == {"café", "casa"}
    # 'prefix' no debe casar substrings interiores como 'águila' o 'a priori'.
    assert "a priori" not in body["words"]


def test_search_suffix_mode(client, auth):
    r = client.get("/words/search?q=rro&mode=suffix", headers=auth)
    assert set(r.json()["words"]) == {"perro"}


def test_search_distinguishes_enye(client, auth):
    # 'ano' (contains) casa con 'ano' pero NO con 'año' (ñ es letra propia).
    r = client.get("/words/search?q=ano", headers=auth)
    words = r.json()["words"]
    assert "ano" in words
    assert "año" not in words


def test_search_escapes_wildcards(client, auth):
    # Un guion bajo debe tratarse como literal, no como comodín LIKE.
    r = client.get("/words/search?q=a_b", headers=auth)
    assert r.json()["total"] == 0


def test_search_include_phrases(client, auth):
    # 'a' (contains) sin locuciones no incluye 'a priori'; con ellas, sí.
    without = client.get("/words/search?q=prior", headers=auth).json()
    assert without["total"] == 0
    with_phrases = client.get(
        "/words/search?q=prior&include_phrases=true", headers=auth
    ).json()
    assert with_phrases["words"] == ["a priori"]


def test_search_invalid_mode_rejected(client, auth):
    r = client.get("/words/search?q=ca&mode=regex", headers=auth)
    assert r.status_code == 422


def test_pattern_underscore_is_one_letter(client, auth):
    # 'c_s_' -> 4 letras, empieza por c y tercera es s: solo 'casa'.
    r = client.get("/words/pattern", params={"p": "c_s_"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["words"] == ["casa"]
    assert body["criterion"] == "pattern=c_s_"


def test_pattern_question_mark_is_one_letter(client, auth):
    # '?' es sinónimo de '_' (más cómodo de teclear en un cliente).
    r = client.get("/words/pattern", params={"p": "?a?a"}, headers=auth)
    assert r.json()["words"] == ["casa"]


def test_pattern_star_is_any_run(client, auth):
    # '*ño' -> termina en 'ño': 'año' y 'ñoño'.
    r = client.get("/words/pattern", params={"p": "*ño"}, headers=auth)
    assert set(r.json()["words"]) == {"año", "ñoño"}


def test_pattern_ignores_accents(client, auth):
    # El patrón se compara con la forma normalizada: 'cafe' encuentra 'café'.
    r = client.get("/words/pattern", params={"p": "_afe"}, headers=auth)
    assert r.json()["words"] == ["café"]


def test_pattern_distinguishes_enye(client, auth):
    # La 'ñ' es letra propia también en los patrones literales.
    assert client.get("/words/pattern", params={"p": "ano"}, headers=auth).json()[
        "words"
    ] == ["ano"]
    assert client.get("/words/pattern", params={"p": "año"}, headers=auth).json()[
        "words"
    ] == ["año"]


def test_pattern_length_filter(client, auth):
    # '*a*' casa con varias; 'length' acota a las de 6 letras: 'águila'.
    r = client.get("/words/pattern", params={"p": "*a*", "length": 6}, headers=auth)
    assert r.json()["words"] == ["águila"]


def test_pattern_percent_is_literal(client, auth):
    # '%' del cliente NO es comodín: se escapa y no casa con nada.
    r = client.get("/words/pattern", params={"p": "%a%"}, headers=auth)
    assert r.json()["total"] == 0


def test_pattern_include_phrases(client, auth):
    without = client.get("/words/pattern", params={"p": "a*i"}, headers=auth).json()
    assert without["total"] == 0
    with_phrases = client.get(
        "/words/pattern", params={"p": "a*i", "include_phrases": "true"}, headers=auth
    ).json()
    assert with_phrases["words"] == ["a priori"]


def test_pattern_too_long_rejected(client, auth):
    r = client.get("/words/pattern", params={"p": "a" * 31}, headers=auth)
    assert r.status_code == 422


def test_exists_returns_official_spelling(client, auth):
    # Sin tilde debe encontrar la palabra y devolver su grafía oficial.
    r = client.get("/words/exists/aguila", headers=auth)
    assert r.status_code == 200
    assert r.json() == {
        "query": "aguila",
        "exists": True,
        "word": "águila",
        "letter_count": 6,
        "is_phrase": False,
        "is_affix": False,
        "is_proper": False,
        "zipf": 3.42,
        "tier": "medium",
    }


def test_exists_unknown_word_is_200(client, auth):
    # "No existe" es una respuesta, no un error.
    r = client.get("/words/exists/xyzabc", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["exists"] is False
    assert body["word"] is None


def test_exists_distinguishes_enye(client, auth):
    assert client.get("/words/exists/ano", headers=auth).json()["word"] == "ano"
    assert client.get("/words/exists/año", headers=auth).json()["word"] == "año"


def test_exists_flags_phrases(client, auth):
    r = client.get("/words/exists/a priori", headers=auth)
    body = r.json()
    assert body["exists"] is True
    assert body["is_phrase"] is True
    assert body["letter_count"] == 7  # los espacios no cuentan


def test_exists_requires_api_key(client):
    assert client.get("/words/exists/casa").status_code == 401


def test_exists_batch_preserves_order(client, auth):
    r = client.get(
        "/words/exists", params={"w": ["casa", "xyzabc", "AGUILA"]}, headers=auth
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert [x["query"] for x in body["results"]] == ["casa", "xyzabc", "AGUILA"]
    assert [x["exists"] for x in body["results"]] == [True, False, True]
    assert body["results"][2]["word"] == "águila"


def test_exists_batch_requires_at_least_one_word(client, auth):
    assert client.get("/words/exists", headers=auth).status_code == 422


def test_exists_batch_rejects_too_many(client, auth):
    r = client.get("/words/exists", params={"w": ["casa"] * 101}, headers=auth)
    assert r.status_code == 422


def test_pattern_excludes_affixes_by_default(client, auth):
    # '-algia' es un sufijo del lemario: no es una palabra jugable.
    assert client.get("/words/pattern", params={"p": "*algia"}, headers=auth).json()["total"] == 0
    with_affixes = client.get(
        "/words/pattern", params={"p": "*algia", "include_affixes": "true"}, headers=auth
    ).json()
    assert with_affixes["words"] == ["-algia"]


def test_pattern_keeps_words_with_inner_hyphen(client, auth):
    # El guion INTERIOR no hace afijo: 'ping-pong' es una palabra compuesta.
    r = client.get("/words/pattern", params={"p": "ping*"}, headers=auth)
    assert r.json()["words"] == ["ping-pong"]


def test_by_length_excludes_affixes(client, auth):
    # De 5 letras hay 4 entradas, pero dos son afijos ('-algia', 'supra-').
    assert set(client.get("/words/by-length/5", headers=auth).json()["words"]) == {
        "perro",
        "ñandú",
    }
    everything = client.get(
        "/words/by-length/5?include_affixes=true", headers=auth
    ).json()
    assert everything["total"] == 4


def test_search_excludes_affixes(client, auth):
    assert client.get("/words/search?q=supra&mode=prefix", headers=auth).json()["total"] == 0
    r = client.get(
        "/words/search?q=supra&mode=prefix&include_affixes=true", headers=auth
    )
    assert r.json()["words"] == ["supra-"]


def test_random_never_returns_an_affix(client, auth):
    # El caso que más importa: /random alimenta la solución de un juego.
    for _ in range(20):
        word = client.get("/words/random?length=5", headers=auth).json()["word"]
        assert word in {"perro", "ñandú"}


def test_exists_reports_affixes_without_hiding_them(client, auth):
    # exists es una consulta, no un filtro: informa, pero nunca oculta.
    affix = client.get("/words/exists/-algia", headers=auth).json()
    assert affix["exists"] is True
    assert affix["is_affix"] is True
    compound = client.get("/words/exists/ping-pong", headers=auth).json()
    assert compound["exists"] is True
    assert compound["is_affix"] is False


def test_tier_filter(client, auth):
    # De 4 letras: casa (5.77) y café (4.6) son 'common'; ñoño (2.6) es 'rare'.
    r = client.get("/words/by-length/4?tier=common", headers=auth)
    assert set(r.json()["words"]) == {"casa", "café"}
    assert client.get("/words/by-length/4?tier=rare", headers=auth).json()["words"] == [
        "ñoño"
    ]


def test_min_zipf_filter(client, auth):
    # min_zipf es "esta frecuencia o más", no un nivel exacto.
    r = client.get("/words/by-length/4?min_zipf=5", headers=auth)
    assert r.json()["words"] == ["casa"]


def test_tier_unknown_means_no_data(client, auth):
    # 'unknown' agrupa las que ninguna fuente conoce, no las rarísimas.
    r = client.get("/words/by-length/7?tier=unknown", headers=auth)
    assert set(r.json()["words"]) == {"ñoñería", "zaherir"}


def test_random_respects_tier(client, auth):
    for _ in range(20):
        word = client.get("/words/random?length=4&tier=common", headers=auth).json()[
            "word"
        ]
        assert word in {"casa", "café"}


def test_pattern_combines_with_tier(client, auth):
    r = client.get(
        "/words/pattern", params={"p": "?a?a", "tier": "common"}, headers=auth
    )
    assert r.json()["words"] == ["casa"]


def test_exists_reports_frequency(client, auth):
    body = client.get("/words/exists/casa", headers=auth).json()
    assert body["zipf"] == 5.77
    assert body["tier"] == "common"
    # Una palabra sin datos se marca 'unknown', no 'rare'.
    assert client.get("/words/exists/zaherir", headers=auth).json()["tier"] == "unknown"


def test_freq_filter_without_frequencies_explains_itself(client, auth, monkeypatch):
    # Un índice sin enriquecer devolvería listas vacías en silencio: mejor 503.
    from app.services import repository

    monkeypatch.setattr(
        repository, "frequency_info", lambda: {"sources": None, "updated_at": None}
    )
    r = client.get("/words/by-length/4?tier=common", headers=auth)
    assert r.status_code == 503
    assert "enrich_frequency" in r.json()["detail"]
    # Sin filtro de frecuencia, el endpoint sigue funcionando igual.
    assert client.get("/words/by-length/4", headers=auth).status_code == 200


def test_invalid_tier_rejected(client, auth):
    assert client.get("/words/by-length/4?tier=easy", headers=auth).status_code == 422


def test_proper_nouns_excluded_by_default(client, auth):
    # 'Madrid' es la única palabra de 6 letras además de 'águila'.
    assert client.get("/words/by-length/6", headers=auth).json()["words"] == ["águila"]
    with_proper = client.get(
        "/words/by-length/6?include_proper=true", headers=auth
    ).json()
    assert set(with_proper["words"]) == {"águila", "Madrid"}


def test_acronyms_are_not_proper_nouns(client, auth):
    # 'CD' va en mayúsculas pero es una sigla: sigue siendo una palabra.
    assert client.get("/words/by-length/2", headers=auth).json()["words"] == ["CD"]


def test_exists_respects_the_case_asked_for(client, auth):
    # 'bruselas' (la col) y 'Bruselas' (la ciudad) comparten forma normalizada:
    # manda lo que escribe quien consulta.
    comun = client.get("/words/exists/bruselas", headers=auth).json()
    assert comun["word"] == "bruselas"
    assert comun["is_proper"] is False
    propio = client.get("/words/exists/Bruselas", headers=auth).json()
    assert propio["word"] == "Bruselas"
    assert propio["is_proper"] is True


def test_exists_prefers_the_common_noun_when_case_does_not_match(client, auth):
    # 'BRUSELAS' no coincide con ninguna de las dos: gana el nombre común.
    assert client.get("/words/exists/BRUSELAS", headers=auth).json()["word"] == "bruselas"


def test_exists_reports_proper_nouns(client, auth):
    assert client.get("/words/exists/Madrid", headers=auth).json()["is_proper"] is True
    assert client.get("/words/exists/CD", headers=auth).json()["is_proper"] is False


def test_random_with_filters(client, auth):
    r = client.get("/words/random?letter=ñ", headers=auth)
    assert r.status_code == 200
    assert r.json()["word"] in {"ñandú", "ñoño", "ñoñería"}


def test_random_no_match_returns_404(client, auth):
    r = client.get("/words/random?letter=a&length=99", headers=auth)
    assert r.status_code == 404


def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["index_ready"] is True
    assert body["word_count"] == 18
    assert body["freq_sources"] == "test"
