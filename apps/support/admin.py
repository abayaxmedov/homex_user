from django.contrib import admin

from apps.support.models import SupportMessage


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ("sender_role", "client", "master", "is_read", "created_at")
    search_fields = ("message", "client__phone", "master__phone")
    list_filter = ("sender_role", "is_read")
