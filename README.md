# Lemario

API en **FastAPI** sobre el lemario de la **RAE**: obtén palabras en español
por primera letra, por número de letras, por patrón o al azar, comprueba si una
palabra existe y consulta su definición. Pensada como base limpia y segura para
proyectos de palabras en español, ya sea desplegándola como servicio o
montándola dentro de otra aplicación.

## Características

- 📚 **Índice local en SQLite** construido desde los
  [Listados RAE de rubenperezm](https://github.com/rubenperezm/ListadosPalabrasRAE).
  La primera construcción es lenta (descarga + indexado); después las búsquedas
  son instantáneas.
- 🔤 Búsqueda **por primera letra** y **por número de letras**, con paginación.
- 🧩 Búsqueda **por patrón con comodines** (`c_s_`, `*ción`), para crucigramas
  y escaleras de palabras.
- ✅ **¿Existe esta palabra?** en una consulta local y barata (`/words/exists`,
  también en lote), pensada para validar los intentos de un juego.
- 🎲 Palabra **aleatoria** con filtros opcionales por letra y/o longitud.
- 📖 **Definiciones** combinando [rae-api.com](https://rae-api.com/) (fuente
  primaria) y *scraping* de [dle.rae.es](https://dle.rae.es/) como respaldo.
  Las definiciones se **cachean** en SQLite; solo se consulta en la red cuando
  faltan o se fuerza con `?force=true`.
- 📊 **Frecuencia de uso** (opcional): cada palabra lleva su valor en escala
  **Zipf** y un nivel (`common`/`medium`/`rare`/`unknown`), para que un juego
  pueda pedir palabras justas en vez de `avugo`. Se rellena con
  `scripts/enrich_frequency.py`.
- 🎵 **Rima consonante** (`/words/rhymes`): palabras que terminan igual que una
  terminación dada, con la tilde estricta (`anto` no incluye `cantó`) y los
  monosílabos como excepción (`ón` incluye `son`).
- 🔒 **Seguridad**: API key opcional, *rate limiting* por IP, CORS configurable,
  *timeouts*/reintentos en las llamadas externas, `/docs` y el detalle de
  `/health` solo desde redes internas, y un modo `production` que se niega a
  arrancar con una configuración insegura.

## Normalización (acentos y ñ)

- Las tildes se ignoran al buscar y agrupar: **`águila` cuenta como letra `a`**.
- La **`ñ` es una letra propia**: `ñandú` se agrupa bajo `ñ`.
- La **longitud** es el número de letras (se ignoran espacios y guiones), de modo
  que `-algia` tiene 5 letras.
- Las palabras conservan siempre su grafía oficial en las respuestas.
- Las locuciones (con espacios, p. ej. `a priori`) se excluyen por defecto;
  inclúyelas con `?include_phrases=true`.
- Los **afijos** del lemario —prefijos con guion final (`supra-`, `hetero-`) y
  sufijos con guion inicial (`-algia`, `-logía`)— **se excluyen por defecto**,
  igual que las locuciones: son elementos compositivos, no palabras jugables.
  Son 453 de las 89.738 entradas, y pesan más de lo que parece en las palabras
  cortas (138 de las 2.142 de 4 letras). Inclúyelos con `?include_affixes=true`.
- El guion **interior** no hace afijo: `ping-pong`, `kung-fu` y `espacio-tiempo`
  son palabras compuestas normales y salen siempre.
- Los **nombres propios** (`Madrid`, `Alzheimer`) también se excluyen por
  defecto (`?include_proper=true` para incluirlos). El criterio es la grafía
  oficial de la RAE, no la frecuencia: `Chile` (el país) y `chile` (el ají) son
  dos entradas distintas, y `mateo` —quien estudia mucho, en Chile— es nombre
  común aunque exista `Mateo`. Las **siglas** (`ADN`, `CD-ROM`) van en
  mayúsculas pero no son nombres propios: esas se quedan.
- Cuando dos entradas comparten forma normalizada (`adonde`/`adónde`,
  `chile`/`Chile`: hay 251 pares), `/words/exists` devuelve la que coincide con
  lo que se escribió; si no coincide ninguna, prefiere el nombre común.
- En `/words/pattern` los comodines actúan sobre la forma normalizada, así que
  `_` casa con cualquier carácter. Con los afijos fuera por defecto apenas se
  nota; si los incluyes, `?p=c_s_` también devolverá `cis-`.

## Requisitos

- Python 3.12+

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (PowerShell: .venv\Scripts\Activate.ps1)
pip install -r requirements.txt
cp .env.example .env              # y edita los valores
```

> **Al cambiar de versión de Python (o de equipo):** dependencias con código
> compilado (`pydantic-core`, `lxml`) traen binarios atados a la versión del
> intérprete (`cp312`, `cp314`, …) y a la arquitectura (`win_amd64`, `win_arm64`).
> Si al arrancar ves `ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'`
> o similar, el venv arrastra binarios de otra versión. Solución: reinstala las
> ruedas correctas para tu intérprete actual —
> `pip install --force-reinstall pydantic-core lxml` — o recrea el venv desde cero
> (`rm -rf .venv` y repite los pasos de arriba). No hace falta cambiar de versión
> de Python: basta con que las ruedas coincidan con el intérprete.

## 1) Construir el índice (primera vez)

```bash
python -m scripts.build_index                 # auto-detecta la última edición
python -m scripts.build_index --file 23-8-1.txt   # fuerza una edición concreta
python -m scripts.build_index --local lista.txt   # desde un fichero local
python -m scripts.build_index --force         # reconstruye el índice
```

La auto-detección consulta la API de GitHub del repositorio y elige el fichero
con la versión más alta (`23-8-1` > `23-8` > `23-2`). El nombre de la edición
usada queda registrado y se ve en `/health`.

> La tabla de palabras se reconstruye desde cero, pero la **caché de
> definiciones se conserva** entre reconstrucciones.

> Si ya tenías un índice de una versión anterior, **no hace falta
> reconstruirlo**: al arrancar, la API añade y rellena sola las columnas
> derivadas que falten (`is_affix`, `is_proper`, frecuencias). En las 89.738
> palabras tarda ~80 ms y solo
> ocurre una vez.

## 2) Enriquecer con frecuencias (opcional pero recomendado)

```bash
pip install wordfreq                       # fuente secundaria
python -m scripts.enrich_frequency         # las tres fuentes
python -m scripts.enrich_frequency --no-crea             # sin CREA
python -m scripts.enrich_frequency --local es_full.txt   # OpenSubtitles local
```

Sin este paso todo queda en `unknown` y la API **avisa con un 503** si intentas
filtrar por frecuencia, en vez de devolver listas vacías sin explicación.

### Antes: descargar CREA

El fichero de frecuencias de la RAE no se puede pedir por red, así que hay que
bajarlo una vez:

1. Ve a **<https://www.rae.es/crea-anotado/>** y descarga el ZIP de frecuencias
   de **lemas**.
2. Descomprímelo y copia `crea_lemas.txt` a **`data/`** (junto al `license.txt`
   que viene en el mismo ZIP, con los términos CC BY-SA 4.0).

`data/` está en el `.gitignore`, así que ni el fichero ni su licencia viajan con
el repositorio: cada quien se lo descarga. Si no está, `enrich_frequency.py`
avisa y sigue con las otras dos fuentes.

Tres fuentes, y cada una entra solo donde la anterior no llega:

1. **[CREA anotado](https://www.rae.es/crea-anotado/)** (RAE). Es la única que
   cuenta **lemas** —su `correr` incluye *corría* y *corrieron*—, que es
   exactamente lo que guarda este índice, y la única que **conserva las
   mayúsculas**: distingue `chile` (el ají, 7,62 por millón) de `Chile` (el
   país, 90,70). **Hay que descargarla a mano** (ver abajo); nunca se pide por
   red.
2. **[wordfreq](https://github.com/rspeer/wordfreq)**: subtítulos, Wikipedia,
   prensa y redes. Aporta lo que a CREA le falta, porque su corpus llega a 2004:
   `wifi` y `tuitear` existen en el lemario y CREA no los conoce.
3. **[OpenSubtitles 2018](https://github.com/hermitdave/FrequencyWords)**: la
   más larga, baja hasta palabras con una sola aparición. Para la cola.

Cobertura sobre el lemario completo: **69,1 %** (54.857 de CREA, 3.710 de
wordfreq, 3.421 de OpenSubtitles). Tarda unos segundos. El 31 % restante no es
un fallo de las fuentes: son entradas del DLE que no aparecen ni una vez en
cientos de millones de palabras (`avugo`, `beudo`, `zaque`).

### Dos decisiones que conviene conocer

**Recalibración.** Las fuentes de respaldo cuentan *formas* sueltas, no lemas,
así que se quedan cortas de forma sistemática: medido sobre las 47.852 palabras
que comparten las tres, la diferencia es de **+0,47** (verbos +1,07, adjetivos
+0,66, adverbios +0,48, sustantivos +0,36 — crece con la flexión, que es
justo la señal de que CREA mide lemas). Los valores de respaldo se llevan a la
escala de CREA para que un mismo nivel signifique lo mismo venga de donde venga.

**Nombres propios contaminando nombres comunes.** Si CREA solo conoce una
palabra **en mayúscula** (`pedro` → `Pedro`), se deja *sin dato* en vez de
preguntar a las otras dos, que ignoran la caja y le darían la frecuencia del
nombre. Son 1.194 entradas, casi todas nombres y topónimos. Gracias a esto
`mateo` (quien estudia mucho, en Chile) es `rare` y no `common`.

### La escala Zipf y los niveles

| Zipf | Nivel | Qué es | Palabras de 5 letras |
|------|-------|--------|----------------------|
| ≥ 4 | `common` | Vocabulario cotidiano | 691 |
| 3 – 4 | `medium` | Se reconoce, no se usa a diario | 872 |
| > 0 y < 3 | `rare` | Aparece, pero poco | 2.530 |
| 0 | `unknown` | Ninguna fuente la registra | 995 |

Zipf es log10 de apariciones por mil millones de palabras: 6 es `de`, 4 ronda
el vocabulario cotidiano, 2 es una palabra que casi nadie usa. `?tier=` pide un
nivel **exacto**; `?min_zipf=` pide *"esta frecuencia o más"*.

## 3) Arrancar la API

```bash
uvicorn app.main:app --reload
```

- Documentación interactiva: `http://127.0.0.1:8000/docs`
- Estado e info del índice: `http://127.0.0.1:8000/health`

`/docs`, `/redoc`, `/openapi.json` y el detalle de `/health` (versión, tamaño
del índice) solo responden a clientes de las **redes internas**
(`LEMARIO_TRUSTED_NETWORKS`, por defecto `127.0.0.0/8` y `::1`); desde fuera,
la documentación da 404 y `/health` solo dice `{"status": "ok", "index_ready": …}`.

## Endpoints

Todos (salvo `/health` y `/`) requieren la cabecera de API key si has
configurado `LEMARIO_API_KEYS`.

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/words/by-letter/{letter}` | Palabras por primera letra. `?limit&offset&include_phrases&include_affixes`&tier&min_zipf |
| `GET` | `/words/by-length/{length}` | Palabras por número de letras. `?limit&offset&include_phrases&include_affixes`&tier&min_zipf |
| `GET` | `/words/search` | Palabras que contienen un substring. `?q&mode&limit&offset&include_phrases&include_affixes`&tier&min_zipf |
| `GET` | `/words/pattern` | Palabras que casan con un patrón con comodines. `?p&length&limit&offset&include_phrases&include_affixes`&tier&min_zipf |
| `GET` | `/words/rhymes` | Palabras que riman en consonante con una terminación. `?ending&limit&offset&include_phrases&include_affixes`&include_proper&tier&min_zipf |
| `GET` | `/words/exists/{palabra}` | ¿Está en el lemario? Devuelve la grafía oficial. |
| `GET` | `/words/exists` | Comprobación en lote. `?w=casa&w=cosa` (hasta 100) |
| `GET` | `/words/random` | Palabra aleatoria. `?letter&length&include_phrases&include_affixes`&tier&min_zipf |
| `GET` | `/definitions/{word}` | Definición. `?force&require_in_list` |
| `GET` | `/health` | Estado del servicio (sin auth) |

### Ejemplos

```bash
# Palabras que empiezan por "ñ" (primeras 5)
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/by-letter/ñ?limit=5"

# Palabras de 5 letras
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/by-length/5?limit=10"

# Palabras que contienen "oñ" (ignora tildes; la ñ es letra propia)
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/search?q=oñ"

# Palabras que empiezan por "trans" (mode=prefix aprovecha el índice)
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/search?q=trans&mode=prefix"

# Palabras que terminan en "ción" (mode=suffix)
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/search?q=ción&mode=suffix"

# Palabras de 4 letras cuya tercera letra es "s" ('_' o '?' = una letra)
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/pattern?p=c_s_&length=4"

# Patrón con '*' (cero o más letras): todo lo que acabe en "nción"
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/pattern?p=*nción"

# Rima consonante: la tilde es estricta. "anto" -> canto, santo (no "cantó");
# "ón" -> canción, corazón y además los monosílabos (son, pon), que no llevan tilde
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/rhymes?ending=ón"

# ¿Existe "arbol"? -> exists: true, word: "árbol" (la búsqueda ignora tildes)
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/exists/arbol"

# Varias de una vez, en el mismo orden de la consulta
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/exists?w=casa&w=cosa&w=zzz"

# Incluir también los afijos del lemario (fuera por defecto)
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/by-length/4?include_affixes=true"

# Solo vocabulario cotidiano: el pool de un juego diario de 5 letras
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/by-length/5?tier=common"

# "Esta frecuencia o más" (Zipf); combinable con cualquier otro filtro
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/pattern?p=c_s_&length=4&min_zipf=4"

# Palabra aleatoria de 4 letras que empiece por "c"
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/words/random?letter=c&length=4"

# Definición de "casa" (usa caché si existe)
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/definitions/casa"

# Forzar nueva consulta ignorando la caché
curl -H "X-API-Key: TU_CLAVE" "http://127.0.0.1:8000/definitions/casa?force=true"
```

## Calidad (CI local)

```bash
pip install -r requirements-dev.txt
python -m scripts.check             # ruff (lint + formato) y pytest; falla si algo falla
python -m scripts.check --fix       # aplica antes los arreglos automáticos de ruff
python -m scripts.check --network   # incluye la prueba real contra rae-api
pytest                              # solo las pruebas, deterministas (sin red)
```

Para que `git commit` lo ejecute solo (una vez por clon):

```bash
git config core.hooksPath .githooks
```

El día que haya un CI remoto (GitHub Actions, etc.), su único paso es
`pip install -r requirements-dev.txt && python -m scripts.check`.

Cubren los casos delicados del español: agrupación de tildes (`águila` bajo `a`),
la `ñ` como letra propia (`ano` ≠ `año`), conteo de letras ignorando
espacios/guiones, autenticación, y la definición de una palabra poco común
(con fuentes simuladas y, opcionalmente, real).

## Docker

La imagen instala las versiones exactas de `requirements.lock` y corre como un
usuario sin privilegios (uid 10001).

```bash
docker build -t lemario .
# La primera vez construye el índice dentro del contenedor (necesita red).
# Monta un volumen para conservar el índice y la caché entre ejecuciones.
# Con Docker Desktop, tu máquina llega con la IP del puente de Docker: para
# poder abrir /docs hay que declarar esas redes como internas.
docker run -p 127.0.0.1:8000:8000 -e LEMARIO_API_KEYS=tu_clave \
  -e LEMARIO_TRUSTED_NETWORKS=127.0.0.0/8,172.16.0.0/12,192.168.0.0/16 \
  -v "${PWD}/data:/app/data" lemario
```

O con **docker-compose** (lee `.env` si existe y monta `./data` como volumen).
Ya publica el puerto solo en `127.0.0.1` y declara las redes internas de Docker:

```bash
cp .env.example .env   # opcional: define LEMARIO_API_KEYS y demás
docker compose up --build
```

En Linux, `./data` debe poder escribirlo el uid del contenedor:
`sudo chown -R 10001:10001 ./data`.

### Pasar a producción más adelante

Hoy está pensado para uso local. Lo que ya está dejado a punto, y lo que se
cambia cuando llegue el momento:

| Qué | Cómo |
|-----|------|
| Rechazar configuraciones inseguras | `LEMARIO_ENVIRONMENT=production`: no arranca sin `LEMARIO_API_KEYS` ni con `LEMARIO_CORS_ORIGINS=*` |
| Quién ve la documentación | `LEMARIO_TRUSTED_NETWORKS` (solo loopback por defecto) |
| Exponerlo a la red | `LEMARIO_BIND=0.0.0.0` en `.env` **y** un proxy inverso con HTTPS (Caddy, Nginx, Traefik) delante |
| IP real del cliente tras el proxy | `FORWARDED_ALLOW_IPS=<IP del proxy>` (nunca `*`). Sin esto, el proxy es "el cliente": el *rate limit* se vuelve global y las redes internas se evalúan mal |
| Varios workers o réplicas | `WEB_CONCURRENCY=N` y `LEMARIO_RATE_LIMIT_STORAGE=redis://…` (instala `redis`); la API avisa al arrancar si falta |
| Actualizar el lemario | Cambia `LEMARIO_LIST_BRANCH` (va fijado a un commit) y reconstruye con `--force` |
| Definiciones | Revisa antes los términos de la RAE y de rae-api.com (ver `NOTICE.md`) |

Pendiente a propósito (solo importa con tráfico real): las consultas de
definiciones usan SQLite y `BeautifulSoup` de forma síncrona dentro de un
endpoint `async`, y la caché de definiciones es SQLite (varios procesos
escribiendo pueden chocar).

## Configuración

Variables de entorno (prefijo `LEMARIO_`, ver `.env.example`):

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `LEMARIO_ENVIRONMENT` | `development` | `production` exige claves y un CORS que no sea `*` |
| `LEMARIO_DATABASE_PATH` | `data/lemario.db` | Ruta del SQLite |
| `LEMARIO_API_KEYS` | *(vacío)* | Claves válidas (CSV). Vacío = API abierta (solo dev) |
| `LEMARIO_API_KEY_HEADER` | `X-API-Key` | Cabecera de la clave |
| `LEMARIO_TRUSTED_NETWORKS` | `127.0.0.0/8,::1/128` | Redes (CIDR, CSV) que ven `/docs` y el detalle de `/health` |
| `LEMARIO_RATE_LIMIT_STORAGE` | `memory://` | Dónde se cuentan las peticiones; `redis://…` con varios workers |
| `LEMARIO_RATE_LIMIT_DEFAULT` | `120/minute` | Límite global por IP |
| `LEMARIO_RATE_LIMIT_DEFINITIONS` | `30/minute` | Límite del endpoint de definiciones |
| `LEMARIO_RATE_LIMIT_EXISTS` | `600/minute` | Límite de `/words/exists` (consulta local, sin red) |
| `LEMARIO_CORS_ORIGINS` | `*` | Orígenes permitidos (CSV) |
| `LEMARIO_HTTP_TIMEOUT` | `10` | Timeout (s) de llamadas externas |
| `LEMARIO_HTTP_RETRIES` | `2` | Reintentos de llamadas externas |
| `LEMARIO_LIST_REPO` | `rubenperezm/ListadosPalabrasRAE` | Repo del lemario |
| `LEMARIO_LIST_BRANCH` | *(un commit)* | Rama, etiqueta o commit del repo (fijado a un commit) |
| `LEMARIO_CREA_PATH` | `data/crea_lemas.txt` | Fichero de lemas de CREA (local, no se descarga) |
| `LEMARIO_FREQ_LIST_URL` | *(OpenSubtitles 2018)* | Lista de frecuencias para `enrich_frequency.py` |

## Notas y limitaciones

- **Fuente primaria de definiciones:** `rae-api.com`. Funciona de forma fiable y
  devuelve las acepciones ya estructuradas.
- **Respaldo `dle.rae.es`:** está implementado, pero la web oficial está
  protegida con Cloudflare y suele responder **403** a clientes HTTP simples.
  Por eso es un respaldo *best-effort*: hacerlo de forma fiable exigiría un
  navegador real. El parser soporta tanto el marcado clásico (`<p class="j">`)
  como el nuevo (acepciones numeradas dentro del `<article>`).
- **Playwright (opcional):** `scripts/fetch_definition_playwright.py` es una
  prueba aparte, fuera de la API, que consulta el DLE con un Chromium real.
  Necesita `pip install -r requirements-dev.txt` y `playwright install chromium`
  (el navegador no viene con el paquete). Uso: `python -m scripts.fetch_definition_playwright casa`.
- **Es un lemario, no un corpus de formas.** Están `correr` y `casa`, no
  `corría` ni `casas`. Para un diccionario es lo correcto; un juego que valide
  los intentos del jugador con `/words/exists` rechazará plurales y verbos
  conjugados. Añadirlos es el siguiente paso natural del proyecto.
- **Las frecuencias son un paso manual.** No se construyen dentro de la imagen
  Docker: hay que ejecutar `scripts/enrich_frequency.py` (y descargar antes el
  fichero de CREA) sobre el volumen de datos.
- Respeta los términos de uso de las fuentes y los límites de tasa para no
  saturarlas.

## Fuentes y licencias

Resumen; la atribución completa y qué implica redistribuir cada cosa está en
[NOTICE.md](NOTICE.md).

| Dato | Fuente | Licencia |
|------|--------|----------|
| Lemario | [Listados RAE de rubenperezm](https://github.com/rubenperezm/ListadosPalabrasRAE) (de [iedra.es](https://iedra.es/)) | Apache-2.0 el repositorio; el contenido es de la RAE |
| Definiciones | [rae-api.com](https://rae-api.com/) y [dle.rae.es](https://dle.rae.es/) | términos de cada fuente |
| Frecuencias (principal) | **[CREA anotado](https://www.rae.es/crea-anotado/)**, Real Academia Española | **CC BY-SA 4.0** |
| Frecuencias (secundaria) | [wordfreq](https://github.com/rspeer/wordfreq) | MIT (código) |
| Frecuencias (cola) | [FrequencyWords / OpenSubtitles 2018](https://github.com/hermitdave/FrequencyWords) | **CC BY-SA 3.0** |

> Las frecuencias proceden del *Corpus de Referencia del Español Actual*
> (**[CREA anotado](https://www.rae.es/crea-anotado/)**) de la **Real Academia
> Española**, publicadas bajo CC BY-SA 4.0; los términos completos vienen en el
> propio ZIP de descarga. Este proyecto no redistribuye esos datos: solo los
> lee de `data/` y los transforma (escala Zipf y niveles de dificultad). Si tú
> **sí** redistribuyes el índice ya enriquecido, las cláusulas *CompartirIgual*
> de CREA y de OpenSubtitles te obligan a citar ambas fuentes y a mantener la
> misma licencia.
