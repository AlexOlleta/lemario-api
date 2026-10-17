FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LEMARIO_DATABASE_PATH=/app/data/lemario.db

WORKDIR /app

RUN groupadd --system --gid 10001 lemario \
    && useradd --system --uid 10001 --gid lemario --home-dir /app --shell /usr/sbin/nologin lemario

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY --chown=lemario:lemario app ./app
COPY --chown=lemario:lemario scripts ./scripts
COPY --chown=lemario:lemario --chmod=755 docker-entrypoint.sh .
RUN mkdir -p /app/data && chown lemario:lemario /app/data

USER lemario

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
