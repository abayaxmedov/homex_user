from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order, OrderStatus, PaymentType
from apps.wallet.models import WalletTransaction
from apps.wallet.services import post_wallet_transaction


@transaction.atomic
def complete_paid_order(order, payment_method):
    """Complete an order once the client has paid, crediting the master's wallet.

    This is the single place the wallet is credited — it runs at PAYMENT time (online
    via Payme's mark_order_paid, or cash via the master's confirm-cash action), not when
    the master submits the check. Idempotent: only acts on an ``awaiting_payment`` order,
    so a duplicate Payme perform / double cash-confirm can't pay the master twice.

    ``payment_method`` is a :class:`PaymentType` value (cash / online).
    Returns ``True`` if the order was completed by this call, ``False`` if it was a no-op.
    """
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status != OrderStatus.AWAITING_PAYMENT:
        return False

    order.status = OrderStatus.COMPLETED
    order.payment_type = payment_method
    order.is_paid = True
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "payment_type", "is_paid", "paid_at", "updated_at"])

    if order.master_id and order.total_amount:
        wallet_method = (
            WalletTransaction.CASH if payment_method == PaymentType.CASH else WalletTransaction.ONLINE
        )
        post_wallet_transaction(
            master=order.master,
            transaction_type=WalletTransaction.IN,
            amount=order.total_amount,
            payment_method=wallet_method,
            description=str(order.service),
            order=order,
        )
    return True
