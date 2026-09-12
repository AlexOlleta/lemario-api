"""Pruebas del enriquecimiento de frecuencias (funciones puras, sin base de datos)."""

from __future__ import annotations

from scripts.enrich_frequency import parse_counts, parse_crea, resolve_zipf

# Dos líneas de cabecera + filas reales (elemento, categoría, abs, norm, norm sin signos).
CREA_SAMPLE = """Elemento\t\tFrecuencia\tFrec. norm.\tFrec. norm
\t\t\tcon signos ort.\tsin signos ort.
casa\tN\t100000\t600.00\t700.00
chile\tN\t1000\t6.50\t7.62
Chile\tN\t12000\t77.00\t90.70
que\tC\t1619865\t11169.58\t12967.73
que\tH\t2015588\t13898.24\t13000.00
,\tY\t8351278\t57585.25\t66855.68
"""


def test_parse_crea_keeps_case_and_sums_categories():
    crea = parse_crea(CREA_SAMPLE)
    # 'chile' y 'Chile' son entradas distintas: es lo que hace útil a CREA.
    assert crea["chile"] == 7.62
    assert crea["Chile"] == 90.70
    # Un mismo lema en dos categorías se suma.
    assert crea["que"] == 12967.73 + 13000.00
    # Los signos de puntuación no son palabras.
    assert "," not in crea


def test_parse_counts_sums_and_totals():
    counts, total = parse_counts("de 100\nCasa 20\ncasa 5\nbasura suelta\n")
    assert counts == {"de": 100, "casa": 25}
    assert total == 125  # el total es el tamaño del corpus, no del lemario


def _wordfreq(zipfs):
    return lambda word, lang: zipfs.get(word, 0.0)


def test_resolve_prefers_crea():
    crea = {"casa": 700.0}
    zipf, source = resolve_zipf("casa", crea, _wordfreq({"casa": 5.77}), {}, 0)
    assert source == "crea"
    assert zipf == 5.85  # log10(700) + 3


def test_resolve_stops_when_crea_only_knows_the_proper_noun():
    # 'pedro' solo existe en CREA como 'Pedro': las otras fuentes ignoran la
    # caja y le darían la frecuencia del nombre. Mejor sin dato que mal dato.
    crea = {"Pedro": 47.30}
    zipf, source = resolve_zipf("pedro", crea, _wordfreq({"pedro": 4.5}), {}, 0)
    assert (zipf, source) == (0.0, None)


def test_resolve_uses_crea_for_the_proper_noun_itself():
    crea = {"Pedro": 47.30}
    zipf, source = resolve_zipf("Pedro", crea, None, {}, 0)
    assert source == "crea"


def test_resolve_falls_back_to_wordfreq_recalibrated():
    # 'wifi' no existe en CREA (corpus hasta 2004) ni como nombre propio.
    zipf, source = resolve_zipf("wifi", {"casa": 700.0}, _wordfreq({"wifi": 4.07}), {}, 0)
    assert source == "wordfreq"
    assert zipf == 4.54  # 4.07 + 0.47 de recalibración a la escala de CREA


def test_resolve_falls_back_to_opensubtitles_last():
    zipf, source = resolve_zipf("zaherir", {}, _wordfreq({}), {"zaherir": 1000}, 423_290_924)
    assert source == "opensubtitles"
    assert zipf == 3.84  # 3.37 + 0.47


def test_resolve_reports_no_data():
    assert resolve_zipf("avugo", {}, _wordfreq({}), {}, 100) == (0.0, None)
