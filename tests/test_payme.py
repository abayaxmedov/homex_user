"""Payme (Paycom) merchant webhook + checkout tests."""
import base64
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.orders.models import Order, OrderInventoryUsage, OrderStatus, PaymentType
from apps.payme.models import PaymeTransaction
from apps.warehouse.models import MasterInventory, WarehouseProduct

WEBHOOK_URL = "/api/v1/payme/"
PAYME_KEY = "test-key"


@pytest.fixture(autouse=True)
def payme_settings(settings):
    settings.PAYME_MERCHANT_ID = "merchant-1"
    settings.PAYME_KEY = PAYME_KEY
    settings.PAYME_TEST_KEY = "sandbox-key"
    settings.PAYME_TEST_MODE = False
    settings.PAYME_ACCOUNT_FIELD = "order_id"
    settings.PAYME_ONE_TIME_PAYMENT = True
    settings.PAYME_ALLOWED_IPS = []
    settings.PAYME_CHECKOUT_URL = ""
    settings.PAYME_RETURN_DEEPLINK = "homex://payment/result"
    settings.PAYME_CHECKOUT_LANG = "uz"


@pytest.fixture
def webhook_client():
    api = APIClient()
    token = base64.b64encode(f"Paycom:{PAYME_KEY}".encode()).decode()
    api.credentials(HTTP_AUTHORIZATION=f"Basic {token}")
    return api


@pytest.fixture
def order(db, client_user, service):
    return Order.objects.create(
        client=client_user,
        service=service,
        address_text="Tashkent",
        lat="41.30000000",
        lng="69.25000000",
        scheduled_date=date.today(),
        scheduled_time=time(10, 0),
        status=OrderStatus.NEW,
        payment_type=PaymentType.ONLINE,
        service_fee=Decimal("100000"),
        total_amount=Decimal("100000"),
    )


AMOUNT_TIYIN = 10_000_000  # 100000 so'm * 100


def rpc(api, method, params, **kwargs):
    return api.post(
        WEBHOOK_URL,
        data={"id": 1, "jsonrpc": "2.0", "method": method, "params": params},
        format="json",
        **kwargs,
    )


def create_tx(api, order, txn_id="tx-1", amount=AMOUNT_TIYIN):
    return rpc(api, "CreateTransaction", {"id": txn_id, "time": 1, "amount": amount, "account": {"order_id": str(order.id)}})


# ---------------------------------------------------------------------------
# Auth + protocol errors
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_missing_auth_returns_permission_denied():
    resp = rpc(APIClient(), "CheckPerformTransaction", {"amount": 1, "account": {}})
    assert resp.status_code == 200
    assert resp.data["error"]["code"] == -32504


@pytest.mark.django_db
def test_wrong_key_returns_permission_denied():
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION="Basic " + base64.b64encode(b"Paycom:wrong").decode())
    resp = rpc(api, "CheckTransaction", {"id": "x"})
    assert resp.data["error"]["code"] == -32504


@pytest.mark.django_db
def test_non_post_returns_transport_error(webhook_client):
    resp = webhook_client.get(WEBHOOK_URL)
    assert resp.status_code == 200
    assert resp.data["error"]["code"] == -32300


@pytest.mark.django_db
def test_bad_json_returns_parse_error(webhook_client):
    resp = webhook_client.post(WEBHOOK_URL, data="{not-json", content_type="application/json")
    assert resp.status_code == 200
    assert resp.data["error"]["code"] == -32700


@pytest.mark.django_db
def test_unknown_method_returns_method_not_found(webhook_client):
    resp = rpc(webhook_client, "NoSuchMethod", {})
    assert resp.data["error"]["code"] == -32601


@pytest.mark.django_db
def test_missing_method_returns_invalid_request(webhook_client):
    resp = webhook_client.post(WEBHOOK_URL, data={"params": {}}, format="json")
    assert resp.data["error"]["code"] == -32600


# ---------------------------------------------------------------------------
# CheckPerformTransaction
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_check_perform_allows_valid_amount(webhook_client, order):
    resp = rpc(webhook_client, "CheckPerformTransaction", {"amount": AMOUNT_TIYIN, "account": {"order_id": str(order.id)}})
    assert resp.data["result"]["allow"] is True


@pytest.mark.django_db
def test_check_perform_amount_mismatch(webhook_client, order):
    resp = rpc(webhook_client, "CheckPerformTransaction", {"amount": 999, "account": {"order_id": str(order.id)}})
    assert resp.data["error"]["code"] == -31001


@pytest.mark.django_db
def test_check_perform_account_not_found(webhook_client):
    resp = rpc(webhook_client, "CheckPerformTransaction", {"amount": AMOUNT_TIYIN, "account": {"order_id": "00000000-0000-0000-0000-000000000000"}})
    assert resp.data["error"]["code"] == -31050
    assert resp.data["error"]["data"] == "order_id"


@pytest.mark.django_db
def test_check_perform_missing_account_field(webhook_client):
    resp = rpc(webhook_client, "CheckPerformTransaction", {"amount": AMOUNT_TIYIN, "account": {}})
    assert resp.data["error"]["code"] == -31050
    assert resp.data["error"]["data"] == "order_id"


# ---------------------------------------------------------------------------
# CreateTransaction — idempotency + one-time-payment
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_transaction_sets_state_1(webhook_client, order):
    resp = create_tx(webhook_client, order)
    assert resp.data["result"]["state"] == 1
    assert PaymeTransaction.objects.filter(transaction_id="tx-1", order=order).exists()


@pytest.mark.django_db
def test_create_transaction_is_idempotent(webhook_client, order):
    first = create_tx(webhook_client, order)
    second = create_tx(webhook_client, order)
    assert first.data["result"]["transaction"] == second.data["result"]["transaction"]
    assert first.data["result"]["create_time"] == second.data["result"]["create_time"]
    assert PaymeTransaction.objects.filter(order=order).count() == 1


@pytest.mark.django_db
def test_create_second_active_transaction_blocked(webhook_client, order):
    create_tx(webhook_client, order, txn_id="tx-1")
    resp = create_tx(webhook_client, order, txn_id="tx-2")
    assert resp.data["error"]["code"] == -31099


# ---------------------------------------------------------------------------
# PerformTransaction
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_perform_marks_order_paid(webhook_client, order):
    create_tx(webhook_client, order)
    resp = rpc(webhook_client, "PerformTransaction", {"id": "tx-1"})
    assert resp.data["result"]["state"] == 2
    order.refresh_from_db()
    assert order.is_paid is True
    assert order.paid_at is not None


@pytest.mark.django_db
def test_perform_is_idempotent(webhook_client, order):
    create_tx(webhook_client, order)
    first = rpc(webhook_client, "PerformTransaction", {"id": "tx-1"})
    second = rpc(webhook_client, "PerformTransaction", {"id": "tx-1"})
    assert first.data["result"]["perform_time"] == second.data["result"]["perform_time"]
    assert second.data["result"]["state"] == 2


# ---------------------------------------------------------------------------
# CancelTransaction
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cancel_before_perform_state_minus_1(webhook_client, order):
    create_tx(webhook_client, order)
    resp = rpc(webhook_client, "CancelTransaction", {"id": "tx-1", "reason": 3})
    assert resp.data["result"]["state"] == -1
    check = rpc(webhook_client, "CheckTransaction", {"id": "tx-1"})
    assert check.data["result"]["reason"] == 3


@pytest.mark.django_db
def test_cancel_after_perform_state_minus_2_and_unpaid(webhook_client, order):
    create_tx(webhook_client, order)
    rpc(webhook_client, "PerformTransaction", {"id": "tx-1"})
    resp = rpc(webhook_client, "CancelTransaction", {"id": "tx-1", "reason": 5})
    assert resp.data["result"]["state"] == -2
    order.refresh_from_db()
    assert order.is_paid is False


@pytest.mark.django_db
def test_cancel_is_idempotent(webhook_client, order):
    create_tx(webhook_client, order)
    first = rpc(webhook_client, "CancelTransaction", {"id": "tx-1", "reason": 3})
    second = rpc(webhook_client, "CancelTransaction", {"id": "tx-1", "reason": 3})
    assert first.data["result"]["state"] == second.data["result"]["state"] == -1
    assert first.data["result"]["cancel_time"] == second.data["result"]["cancel_time"]


@pytest.mark.django_db
def test_cancel_blocked_when_order_completed(webhook_client, order):
    create_tx(webhook_client, order)
    rpc(webhook_client, "PerformTransaction", {"id": "tx-1"})
    Order.objects.filter(pk=order.id).update(status=OrderStatus.COMPLETED)
    resp = rpc(webhook_client, "CancelTransaction", {"id": "tx-1", "reason": 5})
    assert resp.data["error"]["code"] == -31007


# ---------------------------------------------------------------------------
# CheckTransaction / GetStatement
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_check_unknown_transaction(webhook_client):
    resp = rpc(webhook_client, "CheckTransaction", {"id": "nope"})
    assert resp.data["error"]["code"] == -31003


@pytest.mark.django_db
def test_get_statement_returns_transactions(webhook_client, order):
    create_tx(webhook_client, order)
    now_ms = int(timezone.now().timestamp() * 1000)
    resp = rpc(webhook_client, "GetStatement", {"from": now_ms - 100000, "to": now_ms + 100000})
    txns = resp.data["result"]["transactions"]
    assert len(txns) == 1
    assert txns[0]["transaction"] == "tx-1"
    assert txns[0]["account"] == {"order_id": str(order.id)}


# ---------------------------------------------------------------------------
# 12h timeout
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_perform_after_timeout_cancels_and_returns_minus_31008(webhook_client, order):
    create_tx(webhook_client, order)
    old = timezone.now() - timedelta(hours=13)
    PaymeTransaction.objects.filter(transaction_id="tx-1").update(created_at=old)

    resp = rpc(webhook_client, "PerformTransaction", {"id": "tx-1"})
    assert resp.data["error"]["code"] == -31008

    tx = PaymeTransaction.objects.get(transaction_id="tx-1")
    assert tx.state == PaymeTransaction.CANCELED_DURING_INIT
    assert tx.cancel_reason == 4
    order.refresh_from_db()
    assert order.is_paid is False


# ---------------------------------------------------------------------------
# Fiscal detail (sum(items) == amount)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_check_perform_builds_fiscal_items_summing_to_amount(webhook_client, master, client_user, service):
    service.mxik = "00702001001000001"
    service.package_code = "123456"
    service.vat_percent = 12
    service.save()

    product = WarehouseProduct.objects.create(
        name="Filter", unit="dona", quantity=10, sale_price=15000,
        mxik="00509001001000001", package_code="654321", vat_percent=12,
    )
    inv = MasterInventory.objects.create(master=master, warehouse_product=product, quantity=10, unit="dona")

    order = Order.objects.create(
        client=client_user, master=master, service=service,
        address_text="Tashkent", lat="41.30000000", lng="69.25000000",
        scheduled_date=date.today(), scheduled_time=time(10, 0),
        service_fee=Decimal("100000"), inventory_total=Decimal("30000"), total_amount=Decimal("130000"),
    )
    OrderInventoryUsage.objects.create(order=order, inventory=inv, quantity=Decimal("2"), unit_price=Decimal("15000"))

    amount = 13_000_000
    resp = rpc(webhook_client, "CheckPerformTransaction", {"amount": amount, "account": {"order_id": str(order.id)}})
    items = resp.data["result"]["detail"]["items"]

    assert sum(i["price"] * i["count"] for i in items) == amount
    assert {i["code"] for i in items} == {"00702001001000001", "00509001001000001"}
    for i in items:
        assert i["vat_percent"] == 12
        assert i["package_code"] in {"123456", "654321"}


@pytest.mark.django_db
def test_check_perform_without_mxik_skips_fiscal_items(webhook_client, order):
    resp = rpc(webhook_client, "CheckPerformTransaction", {"amount": AMOUNT_TIYIN, "account": {"order_id": str(order.id)}})
    assert resp.data["result"]["allow"] is True
    assert "detail" not in resp.data["result"]


# ---------------------------------------------------------------------------
# Client-facing checkout + status
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_checkout_url_endpoint(client_api, order):
    resp = client_api.post(f"/api/v1/payme/checkout-url/{order.id}/")
    assert resp.status_code == 200
    data = resp.data["data"]
    assert data["amount"] == AMOUNT_TIYIN
    assert data["checkout_url"].startswith("https://checkout.paycom.uz/")
    assert data["post"]["fields"]["account[order_id]"] == str(order.id)


@pytest.mark.django_db
def test_order_status_endpoint_reflects_payment(webhook_client, client_api, order):
    create_tx(webhook_client, order)
    rpc(webhook_client, "PerformTransaction", {"id": "tx-1"})
    resp = client_api.get(f"/api/v1/payme/order-status/{order.id}/")
    assert resp.data["data"]["is_paid"] is True
    assert resp.data["data"]["transaction_state"] == 2
