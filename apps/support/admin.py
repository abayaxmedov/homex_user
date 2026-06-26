from django.contrib import admin

from apps.common.admin_mixins import HomeXModelAdmin
from apps.support.models import SupportMessage


@admin.register(SupportMessage)
class SupportMessageAdmin(HomeXModelAdmin):
    list_display = ("sender_role", "client", "master", "is_read", "created_at")
    search_fields = ("message", "client__phone", "master__phone")
    list_filter = ("sender_role", "is_read")
