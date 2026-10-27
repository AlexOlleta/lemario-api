# Lemario en producción

El [README](README.md) cubre el uso local. Esta guía es el paso siguiente:
exponer la API en un servidor. Todo lo de aquí es opcional y se activa con
configuración, sin tocar el código.

## Lista de comprobación

| Qué | Cómo |
|-----|------|
| Rechazar configuraciones inseguras | `LEMARIO_ENVIRONMENT=production`: no arranca sin `LEMARIO_API_KEYS` ni con `LEMARIO_CORS_ORIGINS=*` |
| Quién ve la documentación | `LEMARIO_TRUSTED_NETWORKS` (solo loopback por defecto) |
| Exponerlo a la red | `LEMARIO_BIND=0.0.0.0` en `.env` **y** un proxy inverso con HTTPS (Caddy, Nginx, Traefik) delante |
| IP real del cliente tras el proxy | `FORWARDED_ALLOW_IPS=<IP o subred del proxy>` (nunca `*`) |
| Varios workers o réplicas | `WEB_CONCURRENCY=N` y `LEMARIO_RATE_LIMIT_STORAGE=redis://…` (instala `redis`); la API avisa al arrancar si falta |
| Actualizar el lemario | Cambia `LEMARIO_LIST_BRANCH` (va fijado a un commit) y reconstruye con `--force` |
| Definiciones | Revisa antes los términos de la RAE y de rae-api.com (ver [NOTICE.md](NOTICE.md)) |

## Detrás de un proxy inverso

Con un proxy delante, todas las peticiones llegan a la API desde la IP del
proxy, normalmente una IP privada de Docker. De ahí salen dos reglas:

- **`FORWARDED_ALLOW_IPS`** debe ser la IP o la subred del proxy (uvicorn acepta
  CIDR). Así toma la IP real del cliente de `X-Forwarded-For`. Sin esto, el
  proxy es "el cliente": el *rate limit* pasa a ser uno solo para todo el mundo.
- **`LEMARIO_TRUSTED_NETWORKS`** no debe incluir redes privadas
  (`172.16.0.0/12`, `192.168.0.0/16`, `10.0.0.0/8`). Si incluye la red del
  proxy, cualquier visitante cuenta como interno y ve `/docs`, `/openapi.json`
  y el detalle de `/health`.

## Índice y volumen de datos

El contenedor guarda el índice y la caché de definiciones en `/app/data`, que
debe ser un volumen persistente con permiso de escritura para el uid 10001.

Si el volumen está vacío, el primer arranque construye el índice (~5 min, la
API no responde mientras tanto) pero **sin frecuencias**. Para usar uno ya
enriquecido, súbelo antes de arrancar:

```bash
# En tu máquina: copia consistente de la base y subida al servidor.
python -c "import sqlite3; sqlite3.connect('data/lemario.db').backup(sqlite3.connect('lemario-upload.db'))"
scp lemario-upload.db usuario@servidor:/tmp/lemario.db

# En el servidor, con la aplicación parada. <volumen> es el volumen montado en
# /app/data (compruébalo con `docker volume ls`).
docker run --rm -v <volumen>:/app/data -v /tmp/lemario.db:/src/lemario.db:ro alpine \
  sh -c 'cp /src/lemario.db /app/data/ && rm -f /app/data/lemario.db-wal /app/data/lemario.db-shm && chown -R 10001:10001 /app/data'
```

El `chown -R` es del **directorio**, no solo del fichero: SQLite necesita crear
`lemario.db-shm` a su lado y, si `/app/data` es de root, todas las consultas
fallan con `attempt to write a readonly database`.

## Healthcheck

La imagen trae un `HEALTHCHECK` en Python contra `/health` (la imagen *slim*
no tiene `curl` ni `wget`), con un margen de arranque de 10 minutos para cubrir
la construcción del índice.

## Desplegar en Coolify

Aplicación desde el repositorio `lemario-api` con el *build pack* **Dockerfile**,
puerto expuesto `8000`.

- **Variables:** `LEMARIO_ENVIRONMENT=production`, `LEMARIO_API_KEYS`,
  `LEMARIO_CORS_ORIGINS` (los dominios que llaman a la API), `WEB_CONCURRENCY=1`
  y `FORWARDED_ALLOW_IPS=<subred de la red coolify>`. En el servidor:
  `docker network inspect coolify --format '{{(index .IPAM.Config 0).Subnet}}'`.
  Deja `LEMARIO_TRUSTED_NETWORKS` con su valor por defecto (ver
  [Detrás de un proxy inverso](#detrás-de-un-proxy-inverso)).
- **Healthcheck:** deja desactivado el de la interfaz de Coolify, que necesita
  `curl` o `wget`; el de la imagen ya lo cubre.
- **Almacenamiento persistente:** un volumen montado en `/app/data`. Su nombre
  es el que muestra Coolify en *Persistent Storage*; úsalo como `<volumen>` en
  [Índice y volumen de datos](#índice-y-volumen-de-datos) para subir tu base.

## Pendiente a propósito

Solo importa con tráfico real: las consultas de definiciones usan SQLite y
`BeautifulSoup` de forma síncrona dentro de un endpoint `async`, y la caché de
definiciones es SQLite (varios procesos escribiendo pueden chocar).
