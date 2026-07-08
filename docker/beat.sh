#!/bin/sh
set -e

# Wait for PostgreSQL and Redis before starting Celery beat
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

# Weekly DB backup (config.settings CELERY_BEAT_SCHEDULE). Schedule state in /tmp
# so it doesn't depend on a writable /app.
echo "==> Starting Celery beat..."
exec celery -A config.celery beat -l info --schedule=/tmp/celerybeat-schedule
