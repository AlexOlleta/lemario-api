FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LEMARIO_DATABASE_PATH=/app/data/lemario.db

WORKDIR /app

# Dependencias primero para aprovechar la caché de capas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

# El entrypoint construye el índice si no existe y luego arranca la API.
ENTRYPOINT ["./docker-entrypoint.sh"]
