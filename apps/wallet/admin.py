from django.contrib import admin

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


@admin.register(WithdrawRequest)
class WithdrawRequestAdmin(HomeXModelAdmin):
    list_display = ("master", "amount", "status", "created_at")
    search_fields = ("master__phone",)
    list_filter = ("status",)


@admin.register(CashHandover)
class CashHandoverAdmin(HomeXModelAdmin):
    """Admin queue: accept (or reject) the cash a master handed over."""

    list_display = ("master", "amount", "status", "created_at")
    search_fields = ("master__phone",)
    list_filter = ("status",)
    actions = ("accept_selected", "reject_selected")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=WithdrawRequest.PENDING)

    def has_add_permission(self, request):
        return False

    @admin.action(description="Naqd pulni qabul qilish (balansdan yechiladi)")
    def accept_selected(self, request, queryset):
        for handover in queryset:
            accept_cash_handover(handover)

    @admin.action(description="So'rovni rad etish")
    def reject_selected(self, request, queryset):
        for handover in queryset:
            reject_cash_handover(handover)


@admin.register(MasterExpense)
class MasterExpenseAdmin(HomeXModelAdmin):
    list_display = ("master", "purpose", "name", "amount", "date")
    search_fields = ("master__phone", "purpose", "name")
    list_filter = ("purpose", "date")
