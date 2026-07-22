from datetime import date, time

from apps.orders.models import Order, OrderStatus, PaymentType
from apps.orders.serializers import OrderCompleteSerializer
from apps.orders.services import complete_paid_order
from apps.wallet.models import MasterWallet, WalletTransaction


def _order(master, client_user, service, status=OrderStatus.ARRIVED):
    return Order.objects.create(
        client=client_user,
        master=master,
        service=service,
        address_text="Tashkent",
        lat="41.30000000",
        lng="69.25000000",
        scheduled_date=date.today(),
        scheduled_time=time(10, 0),
        status=status,
    )


def _submit_check(order):
    return OrderCompleteSerializer(data={"service_fee": "100000"}, context={"order": order})


def test_check_submit_does_not_credit_and_is_not_repeatable(master, client_user, service):
    order = _order(master, client_user, service)

    first = _submit_check(order)
    assert first.is_valid(), first.errors
    first.save()

    order.refresh_from_db()
    # Submitting the check moves the order to awaiting_payment and does NOT credit
    # the wallet — payment (and crediting) happens later.
    assert order.status == OrderStatus.AWAITING_PAYMENT
    assert not WalletTransaction.objects.filter(master=master, transaction_type=WalletTransaction.IN).exists()

    # Re-submitting the check is rejected (no double inventory deduction).
    second = _submit_check(order)
    assert not second.is_valid()
    assert "yuborilgan" in str(second.errors).lower()


def test_cash_confirm_completes_and_credits_once(master, client_user, service):
    order = _order(master, client_user, service)
    s = _submit_check(order)
    assert s.is_valid(), s.errors
    s.save()
    order.refresh_from_db()

    # First cash confirm completes + credits; a second is a no-op (idempotent).
    assert complete_paid_order(order, PaymentType.CASH) is True
    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED
    assert order.is_paid is True
    assert complete_paid_order(order, PaymentType.CASH) is False

    wallet = MasterWallet.objects.get(master=master)
    assert wallet.balance_cash == 100_000
    assert wallet.total_earned == 100_000
    assert (
        WalletTransaction.objects.filter(master=master, transaction_type=WalletTransaction.IN).count() == 1
    )


def test_cannot_submit_check_on_cancelled_order(master, client_user, service):
    order = _order(master, client_user, service, status=OrderStatus.CANCELLED)

    serializer = _submit_check(order)
    assert not serializer.is_valid()

    assert not MasterWallet.objects.filter(master=master, balance_cash__gt=0).exists()
    assert not WalletTransaction.objects.filter(master=master).exists()
