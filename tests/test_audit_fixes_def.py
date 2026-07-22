from datetime import time
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.market.models import MarketOrder, MarketProduct
from apps.orders.models import Order, OrderStatus, PaymentType
from apps.services.models import Service, ServiceCategory
from apps.support.models import SupportChat


def make_order(client, service, status=OrderStatus.NEW, master=None, **extra):
    return Order.objects.create(
        client=client, master=master, service=service,
        address_text="Toshkent", lat="41.31000000", lng="69.24000000",
        scheduled_date=timezone.localdate(), scheduled_time=time(10, 0),
        status=status, **extra,
    )


# --- D1: client-controlled bonus_used is ignored (no self-discount) ---

def test_client_order_create_ignores_bonus_used(client_api, service):
    resp = client_api.post(
        reverse("client-orders"),
        {
            "service": str(service.id),
            "address_text": "Chilonzor",
            "lat": "41.30000000",
            "lng": "69.25000000",
            "scheduled_date": timezone.localdate().isoformat(),
            "scheduled_time": "10:00:00",
            "payment_type": "cash",
            "bonus_used": "999999",
        },
        format="json",
    )
    assert resp.status_code == 201
    order = Order.objects.get(id=resp.data["data"]["id"])
    assert order.bonus_used == 0  # client input ignored


# --- D2: duplicate rating is a clean 400, not a 500 ---

def test_duplicate_rating_returns_400(client_api, client_user, service, master):
    order = make_order(client_user, service, status=OrderStatus.COMPLETED, master=master, total_amount=100000)
    first = client_api.post(reverse("client-order-rate", args=[order.id]), {"rating": 5}, format="json")
    second = client_api.post(reverse("client-order-rate", args=[order.id]), {"rating": 4}, format="json")
    assert first.status_code == 201
    assert second.status_code == 400


# --- D3: favorite with a bad product id is 400/404, not 500 ---

def test_favorite_bad_id_does_not_500(client_api):
    malformed = client_api.post(reverse("client-market-favorite-toggle"), {"product": "not-a-uuid"}, format="json")
    missing = client_api.post(
        reverse("client-market-favorite-toggle"),
        {"product": "00000000-0000-0000-0000-000000000000"},
        format="json",
    )
    assert malformed.status_code == 400
    assert missing.status_code == 404


# --- E2: support unread counter increments atomically ---

def test_touch_chat_increments_unread(db, client_user):
    from apps.support.services import touch_chat

    chat = SupportChat.objects.create(participant_role="client", client=client_user)
    touch_chat(chat, increment_unread=True)
    touch_chat(chat, increment_unread=True)
    chat.refresh_from_db()
    assert chat.unread_by_admin == 2


# --- New flow: submit check -> awaiting_payment (unpaid); cash confirm -> paid ---

def test_check_submit_then_cash_confirm_marks_paid(master_api, client_user, service, master):
    order = make_order(client_user, service, status=OrderStatus.ARRIVED, master=master)

    submit = master_api.post(
        reverse("master-order-complete", args=[order.id]), {"service_fee": "150000"}, format="multipart"
    )
    assert submit.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.AWAITING_PAYMENT
    assert order.is_paid is False  # not paid until the client pays

    confirm = master_api.post(reverse("master-order-confirm-cash", args=[order.id]))
    assert confirm.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED
    assert order.is_paid is True
    assert order.paid_at is not None


# --- F2: a market order isn't re-priced on later edits ---

def test_market_order_price_is_snapshotted(db, client_user):
    product = MarketProduct.objects.create(name="Rozetka", price=Decimal("100"), quantity=10)
    order = MarketOrder.objects.create(
        client=client_user, product=product, quantity=2, delivery_address="X", phone="+998900000000"
    )
    assert order.total_amount == Decimal("200")
    product.price = Decimal("500")
    product.save(update_fields=["price"])
    order.status = MarketOrder.CONFIRMED
    order.save()
    order.refresh_from_db()
    assert order.total_amount == Decimal("200")  # not re-priced to 1000


# --- F3: market order decrements stock and rejects oversell ---

def test_market_order_decrements_stock_and_blocks_oversell(client_api, client_user):
    product = MarketProduct.objects.create(name="Kabel", price=Decimal("5000"), quantity=5)

    over = client_api.post(
        reverse("client-market-orders"),
        {"product": str(product.id), "quantity": 10, "delivery_address": "X", "phone": "+998900000000"},
        format="json",
    )
    assert over.status_code == 400
    product.refresh_from_db()
    assert product.quantity == 5  # unchanged

    ok = client_api.post(
        reverse("client-market-orders"),
        {"product": str(product.id), "quantity": 3, "delivery_address": "X", "phone": "+998900000000"},
        format="json",
    )
    assert ok.status_code == 201
    product.refresh_from_db()
    assert product.quantity == 2  # 5 - 3


# --- F5: dashboard client total_spent is computed live ---

def test_dashboard_client_total_spent_is_live(admin_api, client_user, service):
    make_order(client_user, service, status=OrderStatus.COMPLETED, total_amount=300000)
    make_order(client_user, service, status=OrderStatus.COMPLETED, total_amount=200000)
    make_order(client_user, service, status=OrderStatus.NEW, total_amount=999000)  # not completed

    resp = admin_api.get(reverse("dashboard-client-detail", args=[client_user.id]))
    assert resp.status_code == 200
    assert Decimal(resp.data["data"]["total_spent"]) == Decimal("500000.00")
    assert resp.data["data"]["total_orders"] == 3
