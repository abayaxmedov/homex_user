from celery import shared_task


@shared_task(name="dashboard.create_weekly_backup")
def create_weekly_backup():
    """Weekly automatic database backup (Celery beat).

    Runs on the beat schedule but only produces a backup when the admin has
    auto-backup enabled (dashboard `backups/settings/`).
    """
    from apps.dashboard.backups import auto_backup_enabled, create_backup

    if not auto_backup_enabled():
        return {"skipped": True, "reason": "auto backup disabled"}
    backup = create_backup(source="auto", note="Haftalik avtomatik backup")
    return {"backup": backup.filename, "size_bytes": backup.size_bytes}
