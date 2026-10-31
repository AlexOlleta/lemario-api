# Atribuciones

Lemario no incluye datos de terceros en el repositorio (`data/` está en el
`.gitignore`), pero construye y sirve un índice a partir de ellos. Esta es la
atribución que corresponde a cada fuente.

| Dato | Fuente | Licencia |
|------|--------|----------|
| Lemario (lista de palabras) | [rubenperezm/ListadosPalabrasRAE](https://github.com/rubenperezm/ListadosPalabrasRAE), listados obtenidos de [iedra.es](https://iedra.es/); el contenido original es del *Diccionario de la lengua española* de la **Real Academia Española** | Repositorio: Apache-2.0. Los derechos sobre el contenido de la RAE son de la RAE |
| Femeninos (qué lemas lo tienen) | [Hunspell es_ES](https://github.com/wooorm/dictionaries/tree/main/dictionaries/es), diccionario de LibreOffice del proyecto [RLA-ES](https://github.com/sbosio/rla-es) | GPL-3.0, LGPL-3.0 o MPL-1.1, a elegir (ver `data/hunspell/license`) |
| Frecuencias de uso (principal) | [CREA anotado](https://www.rae.es/crea-anotado/), **Real Academia Española** | CC BY-SA 4.0 |
| Frecuencias (secundaria) | [wordfreq](https://github.com/rspeer/wordfreq) | Código MIT; datos CC BY-SA 4.0 (ver su README) |
| Frecuencias (cola) | [FrequencyWords / OpenSubtitles 2018](https://github.com/hermitdave/FrequencyWords) | CC BY-SA 3.0 |
| Definiciones (opcional) | [rae-api.com](https://rae-api.com/) y [dle.rae.es](https://dle.rae.es/) | Términos de cada fuente |

## Si redistribuyes algo

- **El código** de este repositorio es independiente de los datos: su licencia
  no depende de las de la tabla. Mientras el proyecto no declare una licencia
  propia (no hay fichero `LICENSE`), nadie más tiene permiso de reutilizarlo.
- **El índice ya construido** (`lemario.db`) y las respuestas de la API que
  incluyen frecuencias son obras derivadas de material CC BY-SA: hay que citar
  CREA y OpenSubtitles (y wordfreq si se usó) y publicar esas frecuencias bajo
  la misma licencia.
- **Las definiciones** no están cubiertas por ninguna licencia abierta: antes de
  servirlas públicamente hay que revisar los términos de la RAE y de rae-api.com.
