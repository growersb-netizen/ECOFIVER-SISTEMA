#!/bin/sh
set -e

echo "=== Viral Hub API starting ==="
echo "PORT=${PORT:-8000}"
echo "DATABASE_SYNC_URL=${DATABASE_SYNC_URL:0:40}..."

# Esperar a que Postgres esté disponible (hasta 30s)
echo "Waiting for Postgres..."
for i in $(seq 1 30); do
  python -c "
import psycopg2, os, sys
url = os.environ.get('DATABASE_SYNC_URL','')
try:
    conn = psycopg2.connect(url, connect_timeout=2)
    conn.close()
    print('Postgres ready')
    sys.exit(0)
except Exception as e:
    sys.exit(1)
" && break
  echo "  attempt $i/30 failed, retrying in 1s..."
  sleep 1
done

# Correr migraciones (si falla no bloqueamos el arranque)
echo "Running alembic upgrade head..."
alembic upgrade head || echo "WARNING: alembic failed — continuing anyway"

# Arrancar uvicorn
echo "Starting uvicorn on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
