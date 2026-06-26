from django.contrib import admin

from apps.common.admin_mixins import HomeXModelAdmin
from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(HomeXModelAdmin):
    list_display = ("role", "title", "is_read", "created_at")
    search_fields = ("title", "body", "client__phone", "master__phone")
    list_filter = ("role", "is_read")
