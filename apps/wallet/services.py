from django.db import transaction

from apps.wallet.models import MasterWallet, WalletTransaction, WithdrawRequest


@transaction.atomic
def accept_cash_handover(handover, note=""):
    """Admin accepts the cash a master handed over.

    Reduces the master's cash balance by the requested amount (floored at 0),
    records an outgoing cash transaction and marks the request approved. Returns
    ``True`` if anything changed (i.e. the request was still pending).
    """
    if handover.status != WithdrawRequest.PENDING:
        return False
    wallet, _ = MasterWallet.objects.get_or_create(master=handover.master)
    amount = handover.amount
    wallet.balance_cash = max(wallet.balance_cash - amount, 0)
    wallet.total_withdrawn = wallet.total_withdrawn + amount
    wallet.save(update_fields=["balance_cash", "total_withdrawn", "updated_at"])
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


def reject_cash_handover(handover, note=""):
    """Admin declines a pending cash handover (no balance change)."""
    if handover.status != WithdrawRequest.PENDING:
        return False
    handover.status = WithdrawRequest.REJECTED
    handover.admin_note = note or "Rad etildi"
    handover.save(update_fields=["status", "admin_note", "updated_at"])
    return True
