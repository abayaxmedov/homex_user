from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from unfold.decorators import action

from apps.common.admin_mixins import HomeXModelAdmin
from apps.dashboard.backups import create_backup
from apps.dashboard.models import DashboardBackup


@admin.register(DashboardBackup)
class DashboardBackupAdmin(HomeXModelAdmin):
    list_display = ("filename", "engine", "source", "size_bytes", "created_by", "created_at")
    list_filter = ("source", "engine")
    search_fields = ("filename",)
    readonly_fields = ("filename", "engine", "source", "size_bytes", "created_by", "note")
    # Changelist-level button (like the dashboard "Backup yaratish").
    actions_list = ("create_now",)

    def has_add_permission(self, request):
        return False

    @action(description="Backup yaratish", url_path="create-now")
    def create_now(self, request):
        try:
            backup = create_backup(source=DashboardBackup.MANUAL, created_by=request.user)
            self.message_user(request, f"Backup yaratildi: {backup.filename}", messages.SUCCESS)
        except RuntimeError as exc:
            self.message_user(request, str(exc), messages.ERROR)
        return redirect(reverse("admin:dashboard_dashboardbackup_changelist"))
