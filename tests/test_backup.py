"""Tests for the dashboard database backup API + weekly auto-backup task."""
import pytest
from django.urls import reverse

from apps.dashboard.backups import auto_backup_enabled, create_backup, set_auto_config
from apps.dashboard.models import DashboardBackup


@pytest.fixture(autouse=True)
def isolated_backup_root(settings, tmp_path):
    """Keep test backups out of the repo's real backups/ directory."""
    settings.BACKUP_ROOT = tmp_path / "backups"
    return settings.BACKUP_ROOT


def test_create_backup_via_api_produces_sql_file(admin_api):
    response = admin_api.post(reverse("dashboard-backups"), {}, format="json")

    assert response.status_code == 201
    data = response.data["data"]
    assert data["filename"].endswith(".sql")
    assert data["engine"] == "sqlite"
    assert data["source"] == "manual"

    backup = DashboardBackup.objects.get(id=data["id"])
    assert backup.exists
    content = backup.path.read_text()
    assert "CREATE TABLE" in content  # a real, restorable dump


def test_list_and_download_backup(admin_api):
    admin_api.post(reverse("dashboard-backups"), {}, format="json")

    listing = admin_api.get(reverse("dashboard-backups"))
    assert listing.status_code == 200
    row = listing.data["results"][0]
    assert row["download_url"].endswith("/download/")

    download = admin_api.get(reverse("dashboard-backup-download", args=[row["id"]]))
    assert download.status_code == 200
    assert download["Content-Disposition"].startswith("attachment")
    body = b"".join(download.streaming_content)
    assert b"CREATE TABLE" in body


def test_delete_backup_removes_file_and_row(admin_api):
    response = admin_api.post(reverse("dashboard-backups"), {}, format="json")
    backup = DashboardBackup.objects.get(id=response.data["data"]["id"])
    path = backup.path
    assert path.exists()

    deleted = admin_api.delete(reverse("dashboard-backup-detail", args=[backup.id]))
    assert deleted.status_code == 204
    assert not path.exists()
    assert not DashboardBackup.objects.filter(id=backup.id).exists()


def test_backup_settings_toggle(admin_api):
    get = admin_api.get(reverse("dashboard-backup-settings"))
    assert get.status_code == 200
    assert get.data["data"]["enabled"] is True  # default on

    patch = admin_api.patch(
        reverse("dashboard-backup-settings"), {"enabled": False, "keep": 10}, format="json"
    )
    assert patch.status_code == 200
    assert patch.data["data"]["enabled"] is False
    assert patch.data["data"]["keep"] == 10
    assert auto_backup_enabled() is False


def test_weekly_task_respects_enabled_flag(db):
    from apps.dashboard.tasks import create_weekly_backup

    set_auto_config(enabled=False)
    assert create_weekly_backup()["skipped"] is True
    assert DashboardBackup.objects.count() == 0

    set_auto_config(enabled=True)
    result = create_weekly_backup()
    assert result["backup"].endswith(".sql")
    assert DashboardBackup.objects.filter(source=DashboardBackup.AUTO).exists()


def test_prune_keeps_only_recent(db, settings):
    settings.BACKUP_KEEP = 2
    for _ in range(4):
        create_backup(source=DashboardBackup.AUTO)
    assert DashboardBackup.objects.count() == 2  # older backups pruned
