"""Full database backup service.

Produces a self-contained ``.sql`` dump of the whole database so the data can be
rebuilt if the DB is lost:

- **sqlite** — ``sqlite3`` ``iterdump()`` (pure Python, no external binary).
- **postgresql** — ``pg_dump`` (``--clean --if-exists``) so ``psql < file.sql``
  recreates every table and row.

Backups live under ``settings.BACKUP_ROOT`` (private, never in public MEDIA).
"""
import logging
import os
import subprocess

from django.conf import settings
from django.db import connection
from django.utils import timezone

from apps.dashboard.models import DashboardBackup, DashboardIntegrationSetting

logger = logging.getLogger(__name__)

AUTO_BACKUP_KEY = "auto_backup"
DEFAULT_AUTO_CONFIG = {"enabled": True, "frequency": "weekly", "day_of_week": 1, "hour": 2, "keep": None}


def backup_dir():
    path = settings.BACKUP_ROOT
    path.mkdir(parents=True, exist_ok=True)
    return path


def _engine():
    engine = settings.DATABASES["default"]["ENGINE"]
    if "postgres" in engine:
        return "postgresql"
    if "sqlite" in engine:
        return "sqlite"
    return engine.rsplit(".", 1)[-1]


def _dump_sqlite(out_path):
    connection.ensure_connection()
    raw = connection.connection  # underlying sqlite3.Connection
    with open(out_path, "w", encoding="utf-8") as fh:
        for line in raw.iterdump():
            fh.write(f"{line}\n")


def _dump_postgres(out_path):
    db = settings.DATABASES["default"]
    cmd = [
        "pg_dump",
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        "-h", str(db.get("HOST") or "localhost"),
        "-p", str(db.get("PORT") or 5432),
        "-U", str(db.get("USER") or ""),
        "-d", str(db.get("NAME") or ""),
    ]
    env = {**os.environ, "PGPASSWORD": str(db.get("PASSWORD") or "")}
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            result = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, env=env, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "pg_dump topilmadi. Postgres backup uchun serverga postgresql-client o'rnating."
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump xatosi: {result.stderr.decode(errors='replace')[:500]}")


def create_backup(source=DashboardBackup.MANUAL, created_by=None, note=""):
    """Dump the whole database to ``BACKUP_ROOT`` and record a DashboardBackup."""
    engine = _engine()
    stamp = timezone.localtime().strftime("%Y_%m_%d_%H%M%S")
    filename = f"backup_{stamp}.sql"
    out_path = backup_dir() / filename
    # Guarantee a unique filename even for rapid successive backups.
    if out_path.exists() or DashboardBackup.objects.filter(filename=filename).exists():
        from uuid import uuid4

        filename = f"backup_{stamp}_{uuid4().hex[:6]}.sql"
        out_path = backup_dir() / filename

    if engine == "sqlite":
        _dump_sqlite(out_path)
    elif engine == "postgresql":
        _dump_postgres(out_path)
    else:
        raise RuntimeError(f"Backup qo'llab-quvvatlanmagan DB engine: {engine}")

    backup = DashboardBackup.objects.create(
        filename=filename,
        size_bytes=out_path.stat().st_size,
        engine=engine,
        source=source,
        note=note,
        created_by=created_by if getattr(created_by, "pk", None) else None,
    )
    prune_old_backups()
    logger.info("Database backup created: %s (%s bytes, %s)", filename, backup.size_bytes, source)
    return backup


def prune_old_backups(keep=None):
    """Keep only the newest ``keep`` backups; delete older files + rows."""
    keep = keep if keep is not None else get_auto_config().get("keep") or settings.BACKUP_KEEP
    stale = DashboardBackup.objects.all()[keep:]
    for backup in stale:
        delete_backup(backup)


def delete_backup(backup):
    try:
        if backup.exists:
            backup.path.unlink()
    except OSError:
        logger.exception("Backup faylini o'chirishda xato: %s", backup.filename)
    backup.delete()


# --- Auto-backup config (stored in DashboardIntegrationSetting) --------------

def get_auto_setting():
    setting, _ = DashboardIntegrationSetting.objects.get_or_create(
        key=AUTO_BACKUP_KEY,
        defaults={"title": "Avtomatik backup", "value": dict(DEFAULT_AUTO_CONFIG)},
    )
    return setting


def get_auto_config():
    return {**DEFAULT_AUTO_CONFIG, **(get_auto_setting().value or {})}


def set_auto_config(**changes):
    setting = get_auto_setting()
    setting.value = {**get_auto_config(), **changes}
    setting.save(update_fields=["value", "updated_at"])
    return setting.value


def auto_backup_enabled():
    return bool(get_auto_config().get("enabled", True))
