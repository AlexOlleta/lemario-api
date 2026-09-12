#!/bin/sh
set -e

DB_PATH="${LEMARIO_DATABASE_PATH:-data/lemario.db}"

if [ ! -f "$DB_PATH" ]; then
    echo "Índice no encontrado en $DB_PATH. Construyendo (requiere red)..."
    python -m scripts.build_index || \
        echo "Aviso: no se pudo construir el índice. Monta uno o revisa la red."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
