"""Create a full database backup (.sql) from the CLI / cron.

    python manage.py create_backup            # manual backup
    python manage.py create_backup --auto     # counts as an automatic backup
"""
from django.core.management.base import BaseCommand

from apps.dashboard.backups import create_backup
from apps.dashboard.models import DashboardBackup


class Command(BaseCommand):
    help = "To'liq DB backup (.sql) yaratadi va settings.BACKUP_ROOT ga saqlaydi."

    def add_arguments(self, parser):
        parser.add_argument("--auto", action="store_true", help="Avtomatik backup sifatida belgilash.")
        parser.add_argument("--note", default="", help="Ixtiyoriy izoh.")

    def handle(self, *args, **options):
        source = DashboardBackup.AUTO if options["auto"] else DashboardBackup.MANUAL
        backup = create_backup(source=source, note=options["note"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Backup yaratildi: {backup.filename} ({backup.size_bytes} bytes, {backup.engine}) -> {backup.path}"
            )
        )
