"""Frecuencia de uso: escala Zipf y niveles de dificultad.

El lemario de la RAE incluye desde 'casa' hasta 'avugo'. Sin una medida de uso
real, cualquier juego reparte ambas por igual, que es la diferencia entre
"difícil" e "injusto". Aquí viven las dos reglas puras que traducen los datos
externos a algo con lo que la API pueda filtrar; quien los descarga y los
aplica es scripts/enrich_frequency.py.

La escala **Zipf** (Van Heuven et al., 2014) es log10 de las apariciones por
mil millones de palabras: 6 es 'de', 4 ronda el vocabulario cotidiano y 2 es
una palabra que casi nadie usa. Al ser logarítmica se puede comparar entre
corpus de tamaños distintos, que es justo lo que necesitamos para mezclar
wordfreq con OpenSubtitles.
"""

from __future__ import annotations

import math

# Niveles expuestos por la API. 'unknown' no es "rarísima": es "no tenemos dato".
TIER_COMMON = "common"
TIER_MEDIUM = "medium"
TIER_RARE = "rare"
TIER_UNKNOWN = "unknown"

COMMON_MIN_ZIPF = 4.0
MEDIUM_MIN_ZIPF = 3.0

# Las fuentes no miden lo mismo. CREA cuenta **lemas** (su 'correr' absorbe
# 'corría' y 'corrieron'), que es justo lo que guarda este índice; wordfreq y
# OpenSubtitles cuentan **formas** sueltas, así que se quedan cortas. Medido
# sobre las 47.852 palabras que comparten las tres fuentes, la diferencia es de
# +0,47 de media (mediana +0,46), y crece con la flexión de la categoría:
# verbos +1,07, adjetivos +0,66, adverbios +0,48, sustantivos +0,36.
# Con CREA como fuente principal, llevamos las de respaldo a su escala para que
# un mismo 'tier' signifique lo mismo venga de donde venga.
FALLBACK_ZIPF_OFFSET = 0.47

# Zipf mínimo que asignamos a una palabra que sí aparece en el corpus: 0.0 está
# reservado para "sin datos", así que una aparición real nunca puede valer 0.
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
    # Zipf es log10 por mil millones: por millón x1000, o sea +3 en log10.
    return max(MIN_KNOWN_ZIPF, round(math.log10(per_million) + 3, 2))


def to_crea_scale(zipf: float) -> float:
    """Lleva un Zipf de las fuentes de respaldo a la escala de CREA."""
    if zipf <= 0:
        return 0.0
    return round(zipf + FALLBACK_ZIPF_OFFSET, 2)
