#!/bin/sh
set -e

# Wait for PostgreSQL to become reachable
echo "==> Waiting for database..."
python - <<'PYEOF'
import os, socket, time, urllib.parse

url = os.environ.get("DATABASE_URL", "")
if url.startswith("postgres"):
    p = urllib.parse.urlparse(url)
    host, port = p.hostname, p.port or 5432
    for attempt in range(30):
        try:
            s = socket.create_connection((host, port), timeout=2)
            s.close()
            print(f"Database is ready at {host}:{port}")
            break
        except OSError:
            print(f"  [{attempt + 1}/30] Waiting for {host}:{port}...")
            time.sleep(2)
    else:
        print("ERROR: Database did not become available in time")
        raise SystemExit(1)
PYEOF

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "==> Starting Gunicorn (uvicorn worker)..."
exec gunicorn config.asgi:application \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${GUNICORN_WORKERS:-4}" \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --keep-alive 5 \
    --access-logfile -
