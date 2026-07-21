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
def post_wallet_transaction(*, master, transaction_type, amount, payment_method, description="", order=None):
    """Create a :class:`WalletTransaction` AND move the wallet balance atomically.

    Single source of truth so a ledger row can't be written without the matching
    balance change. IN credits, OUT debits the cash/online balance that matches
    ``payment_method``. Wallet row is locked; balance updates use ``F()``.
    """
    if amount <= 0:
        raise serializers.ValidationError({"amount": "Summa musbat bo'lishi kerak"})
    wallet, _ = MasterWallet.objects.get_or_create(master=master)
    wallet = MasterWallet.objects.select_for_update().get(pk=wallet.pk)
    balance_field = "balance_cash" if payment_method == WalletTransaction.CASH else "balance_online"
    if transaction_type == WalletTransaction.IN:
        updates = {balance_field: F(balance_field) + amount, "total_earned": F("total_earned") + amount}
    else:
        if getattr(wallet, balance_field) < amount:
            raise serializers.ValidationError({"amount": "Balans yetarli emas"})
        updates = {balance_field: F(balance_field) - amount, "total_withdrawn": F("total_withdrawn") + amount}
    MasterWallet.objects.filter(pk=wallet.pk).update(updated_at=timezone.now(), **updates)
    return WalletTransaction.objects.create(
        master=master,
        transaction_type=transaction_type,
        amount=amount,
        description=description,
        payment_method=payment_method,
        order=order,
    )


@transaction.atomic
def reverse_wallet_transaction(txn):
    """Undo a WalletTransaction's balance effect (for delete). Locked; guards negative.

    Reversing an IN debits the balance back — rejected if the master already spent it.
    """
    wallet, _ = MasterWallet.objects.get_or_create(master=txn.master)
    wallet = MasterWallet.objects.select_for_update().get(pk=wallet.pk)
    balance_field = "balance_cash" if txn.payment_method == WalletTransaction.CASH else "balance_online"
    if txn.transaction_type == WalletTransaction.IN:
        if getattr(wallet, balance_field) < txn.amount:
            raise serializers.ValidationError(
                {"amount": "Bu tranzaksiyani bekor qilib bo'lmaydi — balans yetarli emas (mablag' sarflangan)"}
            )
        updates = {balance_field: F(balance_field) - txn.amount, "total_earned": F("total_earned") - txn.amount}
    else:
        updates = {balance_field: F(balance_field) + txn.amount, "total_withdrawn": F("total_withdrawn") - txn.amount}
    MasterWallet.objects.filter(pk=wallet.pk).update(updated_at=timezone.now(), **updates)


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
