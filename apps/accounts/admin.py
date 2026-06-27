from django.contrib import admin
from django.utils import timezone

from apps.accounts.models import Client, FCMDevice, Master, MasterApprovalStatus, OTPRecord
from apps.common.admin_mixins import HomeXModelAdmin


@admin.register(Client)
class ClientAdmin(HomeXModelAdmin):
    list_display = ("phone", "first_name", "last_name", "language", "is_active", "created_at")
    search_fields = ("phone", "first_name", "last_name")
    list_filter = ("language", "is_active", "notifications_enabled", "push_enabled")


@admin.register(Master)
class MasterAdmin(HomeXModelAdmin):
    list_display = (
        "phone",
        "full_name",
        "specialization",
        "approval_status",
        "rating",
        "is_online",
        "is_available",
        "last_location_at",
        "is_active",
    )
    search_fields = ("phone", "first_name", "last_name", "specialization")
    list_filter = ("approval_status", "is_online", "is_available", "is_active", "language")
    readonly_fields = ("approved_at",)
    actions = ("approve_masters", "reject_masters")

    @admin.action(description="Tanlangan ustalarni tasdiqlash")
    def approve_masters(self, request, queryset):
        queryset.update(
            approval_status=MasterApprovalStatus.APPROVED,
            is_active=True,
            rejected_reason="",
            approved_at=timezone.now(),
        )

    @admin.action(description="Tanlangan ustalarni rad etish")
    def reject_masters(self, request, queryset):
        queryset.update(
            approval_status=MasterApprovalStatus.REJECTED,
            is_active=False,
            approved_at=None,
        )


@admin.register(OTPRecord)
class OTPRecordAdmin(HomeXModelAdmin):
    list_display = ("phone", "code", "is_used", "attempts", "expires_at", "created_at")
    search_fields = ("phone",)
    list_filter = ("is_used",)


@admin.register(FCMDevice)
class FCMDeviceAdmin(HomeXModelAdmin):
    list_display = ("role", "platform", "is_active", "created_at")
    search_fields = ("token",)
    list_filter = ("role", "platform", "is_active")
