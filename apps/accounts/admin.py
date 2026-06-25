from django.contrib import admin

from apps.accounts.models import Client, FCMDevice, Master, OTPRecord


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("phone", "first_name", "last_name", "language", "is_active", "created_at")
    search_fields = ("phone", "first_name", "last_name")
    list_filter = ("language", "is_active", "notifications_enabled", "push_enabled")


@admin.register(Master)
class MasterAdmin(admin.ModelAdmin):
    list_display = (
        "phone",
        "full_name",
        "specialization",
        "rating",
        "is_online",
        "is_available",
        "last_location_at",
        "is_active",
    )
    search_fields = ("phone", "first_name", "last_name", "specialization")
    list_filter = ("is_online", "is_available", "is_active", "language")


@admin.register(OTPRecord)
class OTPRecordAdmin(admin.ModelAdmin):
    list_display = ("phone", "code", "is_used", "attempts", "expires_at", "created_at")
    search_fields = ("phone",)
    list_filter = ("is_used",)


@admin.register(FCMDevice)
class FCMDeviceAdmin(admin.ModelAdmin):
    list_display = ("role", "platform", "is_active", "created_at")
    search_fields = ("token",)
    list_filter = ("role", "platform", "is_active")
