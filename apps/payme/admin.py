from django.contrib import admin

from apps.common.admin_mixins import HomeXModelAdmin
from apps.payme.models import PaymeTransaction


@admin.register(PaymeTransaction)
class PaymeTransactionAdmin(HomeXModelAdmin):
    list_display = ("transaction_id", "order", "amount", "state", "cancel_reason", "created_at")
    list_filter = ("state", "cancel_reason", "created_at")
    search_fields = ("transaction_id", "order__id")
    ordering = ("-created_at",)
    readonly_fields = (
        "transaction_id",
        "order",
        "amount",
        "state",
        "fiscal_data",
        "cancel_reason",
        "created_at",
        "updated_at",
        "performed_at",
        "cancelled_at",
    )
