from datetime import date, time

from apps.orders.models import Order, OrderStatus, PaymentType
from apps.orders.serializers import OrderCompleteSerializer
from apps.wallet.models import MasterWallet, WalletTransaction


def _cash_order(master, client_user, service):
    return Order.objects.create(
        client=client_user,
        master=master,
        service=service,
        address_text="Tashkent",
        lat="41.30000000",
        lng="69.25000000",
        scheduled_date=date.today(),
        scheduled_time=time(10, 0),
        status=OrderStatus.ARRIVED,
        payment_type=PaymentType.CASH,
    )


def _complete(order):
    serializer = OrderCompleteSerializer(data={"service_fee": "100000"}, context={"order": order})
    return serializer


def test_cash_order_complete_twice_does_not_double_credit(master, client_user, service):
    order = _cash_order(master, client_user, service)

    first = _complete(order)
    assert first.is_valid(), first.errors
    first.save()

    order.refresh_from_db()
    # Ikkinchi marta yakunlash rad etiladi (pul qayta qo'shilmaydi).
    second = _complete(order)
    assert not second.is_valid()
    assert "yakunlangan" in str(second.errors).lower()

    wallet = MasterWallet.objects.get(master=master)
    assert wallet.balance_cash == 100_000  # 200_000 bo'lsa -> double-credit bug
    assert wallet.total_earned == 100_000
    assert (
        WalletTransaction.objects.filter(
            master=master, transaction_type=WalletTransaction.IN
        ).count()
        == 1
    )


def test_cannot_complete_cancelled_order(master, client_user, service):
    order = _cash_order(master, client_user, service)
    order.status = OrderStatus.CANCELLED
    order.save(update_fields=["status"])

    serializer = _complete(order)
    assert not serializer.is_valid()

    # Bekor qilingan buyurtma yakunlanmagani uchun hamyon kreditlanmaydi.
    assert not MasterWallet.objects.filter(master=master, balance_cash__gt=0).exists()
    assert not WalletTransaction.objects.filter(master=master).exists()
