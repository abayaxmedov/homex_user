from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from unfold.decorators import action

from apps.common.admin_mixins import HomeXModelAdmin
from apps.wallet.models import CashHandover, MasterExpense, MasterWallet, WalletTransaction, WithdrawRequest
from apps.wallet.services import accept_cash_handover, reject_cash_handover


@admin.register(MasterWallet)
class MasterWalletAdmin(HomeXModelAdmin):
    list_display = ("master", "balance_online", "balance_cash", "total_earned", "total_withdrawn", "updated_at")
    search_fields = ("master__phone",)


@admin.register(WalletTransaction)
class WalletTransactionAdmin(HomeXModelAdmin):
    list_display = ("master", "transaction_type", "amount", "payment_method", "order", "created_at")
    search_fields = ("master__phone", "description")
    list_filter = ("transaction_type", "payment_method")


class CashHandoverActionsMixin:
    """Shared accept/reject actions for cash handovers: per-row buttons + bulk."""

    actions = ("accept_selected", "reject_selected")
    actions_row = ("accept_row", "reject_row")

    def _changelist_url(self):
        meta = self.model._meta
        return reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")

    @action(description="Tasdiqlash", url_path="accept-cash")
    def accept_row(self, request, object_id):
        handover = WithdrawRequest.objects.filter(pk=object_id).first()
        if handover and accept_cash_handover(handover):
            self.message_user(request, "Naqd pul qabul qilindi, master balansidan yechildi.", messages.SUCCESS)
        else:
            self.message_user(request, "So'rov topilmadi yoki allaqachon yopilgan.", messages.WARNING)
        return redirect(self._changelist_url())

    @action(description="Rad etish", url_path="reject-cash")
    def reject_row(self, request, object_id):
        handover = WithdrawRequest.objects.filter(pk=object_id).first()
        if handover and reject_cash_handover(handover):
            self.message_user(request, "So'rov rad etildi.", messages.SUCCESS)
        else:
            self.message_user(request, "So'rov topilmadi yoki allaqachon yopilgan.", messages.WARNING)
        return redirect(self._changelist_url())

    @admin.action(description="Naqd pulni qabul qilish (balansdan yechiladi)")
    def accept_selected(self, request, queryset):
        done = sum(1 for handover in queryset if accept_cash_handover(handover))
        self.message_user(request, f"{done} ta so'rov tasdiqlandi.", messages.SUCCESS)

    @admin.action(description="So'rovlarni rad etish")
    def reject_selected(self, request, queryset):
        done = sum(1 for handover in queryset if reject_cash_handover(handover))
        self.message_user(request, f"{done} ta so'rov rad etildi.", messages.SUCCESS)


@admin.register(WithdrawRequest)
class WithdrawRequestAdmin(CashHandoverActionsMixin, HomeXModelAdmin):
    list_display = ("master", "amount", "status", "admin_note", "created_at")
    search_fields = ("master__phone",)
    list_filter = ("status",)


@admin.register(CashHandover)
class CashHandoverAdmin(CashHandoverActionsMixin, HomeXModelAdmin):
    """Admin queue: accept (or reject) the cash a master handed over."""

    list_display = ("master", "amount", "status", "created_at")
    search_fields = ("master__phone",)
    list_filter = ("status",)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=WithdrawRequest.PENDING)

    def has_add_permission(self, request):
        return False


@admin.register(MasterExpense)
class MasterExpenseAdmin(HomeXModelAdmin):
    list_display = ("master", "purpose", "name", "amount", "date")
    search_fields = ("master__phone", "purpose", "name")
    list_filter = ("purpose", "date")
