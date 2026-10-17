"""Frecuencia de uso: escala Zipf y niveles de dificultad.

Zipf (Van Heuven et al., 2014) es log10 de las apariciones por mil millones de
palabras: 6 es 'de', 4 el vocabulario cotidiano, 2 una palabra que casi nadie
usa. Al ser logarítmica permite mezclar corpus de tamaños distintos. Los datos
los descarga y aplica scripts/enrich_frequency.py.
"""

from __future__ import annotations

import math

TIER_COMMON = "common"
TIER_MEDIUM = "medium"
TIER_RARE = "rare"
TIER_UNKNOWN = "unknown"

COMMON_MIN_ZIPF = 4.0
MEDIUM_MIN_ZIPF = 3.0

# CREA cuenta lemas y wordfreq/OpenSubtitles formas sueltas, así que se quedan
# cortas: medido sobre las 47.852 palabras comunes a las tres, +0,47 de media.
# Se suma a las de respaldo para que un mismo 'tier' signifique lo mismo.
FALLBACK_ZIPF_OFFSET = 0.47

# 0.0 significa "sin datos": una aparición real nunca puede valer 0.
MIN_KNOWN_ZIPF = 0.01


def count_to_zipf(count: int, corpus_total: int) -> float:
    """Pasa 'apariciones en un corpus' a la escala Zipf. 0.0 = sin datos."""
    if count <= 0 or corpus_total <= 0:
        return 0.0
    zipf = math.log10(count / corpus_total * 1_000_000_000)
    return max(MIN_KNOWN_ZIPF, round(zipf, 2))


def tier_for(zipf: float) -> str:
    """Nivel de dificultad a partir del Zipf."""
    if zipf >= COMMON_MIN_ZIPF:
        return TIER_COMMON
    if zipf >= MEDIUM_MIN_ZIPF:
        return TIER_MEDIUM
    if zipf > 0:
        return TIER_RARE
    return TIER_UNKNOWN


def fpm_to_zipf(per_million: float) -> float:
    """Pasa 'apariciones por millón' (como las publica CREA) a escala Zipf."""
    if per_million <= 0:
        return 0.0
    # Por millón x1000 respecto a por mil millones: +3 en log10.
    return max(MIN_KNOWN_ZIPF, round(math.log10(per_million) + 3, 2))


def to_crea_scale(zipf: float) -> float:
    """Lleva un Zipf de las fuentes de respaldo a la escala de CREA."""
    if zipf <= 0:
        return 0.0
    return round(zipf + FALLBACK_ZIPF_OFFSET, 2)
