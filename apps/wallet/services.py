from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from apps.wallet.models import MasterWallet, WalletTransaction, WithdrawRequest


@transaction.atomic
def accept_cash_handover(handover, note=""):
    """Admin accepts the cash a master handed over.

    Reduces the master's cash balance by the requested amount,
    records an outgoing cash transaction and marks the request approved. Returns
    ``True`` if anything changed (i.e. the request was still pending).
    """
    handover = WithdrawRequest.objects.select_for_update().select_related("master").get(pk=handover.pk)
    if handover.status != WithdrawRequest.PENDING:
        return False
    amount = handover.amount
    if amount <= 0:
        raise serializers.ValidationError("Pul yechish summasi musbat bo'lishi kerak")
    wallet, _ = MasterWallet.objects.select_for_update().get_or_create(master=handover.master)
    if wallet.balance_cash < amount:
        raise serializers.ValidationError("Naqd balans yetarli emas")
    MasterWallet.objects.filter(pk=wallet.pk).update(
        balance_cash=F("balance_cash") - amount,
        total_withdrawn=F("total_withdrawn") + amount,
        updated_at=timezone.now(),
    )
    WalletTransaction.objects.create(
        master=handover.master,
        transaction_type=WalletTransaction.OUT,
        amount=amount,
        description="Naqd pul admin tomonidan qabul qilindi",
        payment_method=WalletTransaction.CASH,
    )
    handover.status = WithdrawRequest.APPROVED
    handover.admin_note = note or "Naqd qabul qilindi"
    handover.save(update_fields=["status", "admin_note", "updated_at"])
    return True


@transaction.atomic
def reject_cash_handover(handover, note=""):
    """Admin declines a pending cash handover (no balance change)."""
    handover = WithdrawRequest.objects.select_for_update().get(pk=handover.pk)
    if handover.status != WithdrawRequest.PENDING:
        return False
    handover.status = WithdrawRequest.REJECTED
    handover.admin_note = note or "Rad etildi"
    handover.save(update_fields=["status", "admin_note", "updated_at"])
    return True
