from django.contrib import admin

from apps.wallet.models import MasterExpense, MasterWallet, WalletTransaction, WithdrawRequest


@admin.register(MasterWallet)
class MasterWalletAdmin(admin.ModelAdmin):
    list_display = ("master", "balance_online", "balance_cash", "total_earned", "total_withdrawn", "updated_at")
    search_fields = ("master__phone",)


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("master", "transaction_type", "amount", "payment_method", "order", "created_at")
    search_fields = ("master__phone", "description")
    list_filter = ("transaction_type", "payment_method")


@admin.register(WithdrawRequest)
class WithdrawRequestAdmin(admin.ModelAdmin):
    list_display = ("master", "amount", "status", "created_at")
    search_fields = ("master__phone",)
    list_filter = ("status",)


@admin.register(MasterExpense)
class MasterExpenseAdmin(admin.ModelAdmin):
    list_display = ("master", "purpose", "name", "amount", "date")
    search_fields = ("master__phone", "purpose", "name")
    list_filter = ("purpose", "date")
