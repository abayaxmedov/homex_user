#!/bin/sh
set -e

# Wait for PostgreSQL and Redis before starting worker
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
        raise SystemExit(1)
PYEOF

echo "==> Waiting for Redis..."
python - <<'PYEOF'
import os, socket, time, urllib.parse

url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
p = urllib.parse.urlparse(url)
host, port = p.hostname, p.port or 6379
for attempt in range(30):
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        print(f"Redis is ready at {host}:{port}")
        break
    except OSError:
        print(f"  [{attempt + 1}/30] Waiting for {host}:{port}...")
        time.sleep(2)
else:
    raise SystemExit(1)
PYEOF

export DJANGO_SETTINGS_MODULE=config.settings

echo "==> Starting Celery worker..."
exec celery -A config.celery worker -l info --concurrency 4
