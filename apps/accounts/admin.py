from django.contrib import admin
from django.utils import timezone

from apps.accounts.models import (
    BlockedMaster,
    Client,
    FCMDevice,
    Master,
    MasterApplication,
    MasterApprovalStatus,
    OTPRecord,
)
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
    list_filter = ("approval_status", "is_blocked", "is_online", "is_available", "is_active", "language")
    readonly_fields = ("approved_at", "blocked_at")
    actions = ("approve_masters", "reject_masters", "block_masters", "unblock_masters")

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

    @admin.action(description="Tanlangan ustalarni bloklash")
    def block_masters(self, request, queryset):
        for master in queryset:
            master.block()
            master.save(update_fields=["is_blocked", "is_active", "is_available", "is_online", "block_reason", "blocked_at", "updated_at"])

    @admin.action(description="Tanlangan ustalarni blokdan chiqarish")
    def unblock_masters(self, request, queryset):
        for master in queryset:
            master.unblock()
            master.save(update_fields=["is_blocked", "is_active", "block_reason", "blocked_at", "updated_at"])


@admin.register(MasterApplication)
class MasterApplicationAdmin(MasterAdmin):
    """Separate admin listing for masters awaiting approval (non-active)."""

    list_display = (
        "phone",
        "full_name",
        "specialization",
        "approval_status",
        "created_at",
    )
    list_filter = ("specialization", "language")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(approval_status=MasterApprovalStatus.PENDING)

    def has_add_permission(self, request):
        # Applications are created through master registration, not by hand.
        return False


@admin.register(BlockedMaster)
class BlockedMasterAdmin(MasterAdmin):
    """Separate admin listing for blocked masters with block/unblock actions."""

    list_display = ("phone", "full_name", "specialization", "block_reason", "blocked_at")
    list_filter = ("specialization", "language")
    actions = ("unblock_masters",)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_blocked=True)

    def has_add_permission(self, request):
        return False

    @admin.action(description="Tanlangan ustalarni blokdan chiqarish")
    def unblock_masters(self, request, queryset):
        for master in queryset:
            master.unblock()
            master.save(update_fields=["is_blocked", "is_active", "block_reason", "blocked_at", "updated_at"])


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
