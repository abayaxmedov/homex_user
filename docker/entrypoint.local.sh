#!/bin/sh
# Local development entrypoint — runs the ASGI server (uvicorn) so that
# WebSockets (/ws/...) work. Production entrypoint.sh is untouched.
set -e

echo "==> Waiting for Postgres..."
python - <<'PYEOF'
import os, socket, time, urllib.parse
p = urllib.parse.urlparse(os.environ.get("DATABASE_URL", ""))
host, port = p.hostname or "db", p.port or 5432
for i in range(30):
    try:
        socket.create_connection((host, port), timeout=2).close()
        print(f"Postgres ready at {host}:{port}")
        break
    except OSError:
        print(f"  [{i + 1}/30] waiting for {host}:{port} ...")
        time.sleep(2)
else:
    raise SystemExit("ERROR: Postgres did not become available")
PYEOF

echo "==> Waiting for Redis..."
python - <<'PYEOF'
import os, socket, time, urllib.parse
p = urllib.parse.urlparse(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
host, port = p.hostname or "redis", p.port or 6379
for i in range(30):
    try:
        socket.create_connection((host, port), timeout=2).close()
        print(f"Redis ready at {host}:{port}")
        break
    except OSError:
        print(f"  [{i + 1}/30] waiting for {host}:{port} ...")
        time.sleep(2)
else:
    raise SystemExit("ERROR: Redis did not become available")
PYEOF

export DJANGO_SETTINGS_MODULE=config.settings
export PYTHONPATH=/app

echo "==> Applying migrations..."
python manage.py migrate --noinput

echo "==> Starting Uvicorn (ASGI + WebSockets, auto-reload) on :${BACKEND_PORT:-8000}"
exec uvicorn config.asgi:application \
    --host 0.0.0.0 \
    --port "${BACKEND_PORT:-8000}" \
    --reload
