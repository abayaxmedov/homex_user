"""Tests for: market product delete, client device-order prefill, and the
Unfold admin (order usta/shogird inline + cash-handover accept queue)."""
from datetime import date, time
from decimal import Decimal

import pytest
from django.test import Client as DjangoClient
from django.urls import reverse

from apps.accounts.models import Master, MasterApprovalStatus
from apps.market.models import MarketCategory, MarketOrder, MarketProduct
from apps.orders.models import Order, OrderMaster
from apps.profiles.models import ClientAddress, ClientDevice
from apps.wallet.models import MasterWallet, WithdrawRequest


def _make_order(client_user, service):
    return Order.objects.create(
        client=client_user,
        service=service,
        address_text="Chilonzor",
        lat="41.30000000",
        lng="69.24000000",
        scheduled_date=date.today(),
        scheduled_time=time(10, 0),
    )


# --- Task 3: dashboard market product DELETE ---------------------------------

def test_dashboard_market_product_delete_without_orders_hard_deletes(admin_api):
    category = MarketCategory.objects.create(name="Asbob", slug="asbob-del")
    product = MarketProduct.objects.create(category=category, name="Drel", price=Decimal("300000"), quantity=3)

    response = admin_api.delete(reverse("dashboard-market-product-detail", args=[product.id]))

    assert response.status_code == 200
    assert response.data["data"]["deleted"] is True
    assert not MarketProduct.objects.filter(id=product.id).exists()


def test_dashboard_market_product_delete_with_orders_archives(admin_api, client_user):
    # MarketOrder.product is PROTECT -> a product with orders must not 500 on delete.
    category = MarketCategory.objects.create(name="Mebel", slug="mebel-del")
    product = MarketProduct.objects.create(category=category, name="Stul", price=Decimal("150000"), quantity=5)
    MarketOrder.objects.create(
        client=client_user, product=product, quantity=1, delivery_address="Chilonzor", phone="+998900000001"
    )

    response = admin_api.delete(reverse("dashboard-market-product-detail", args=[product.id]))

    assert response.status_code == 200
    assert response.data["data"]["archived"] is True
    product.refresh_from_db()
    assert product.is_active is False  # archived, not hard-deleted
    assert MarketProduct.objects.filter(id=product.id).exists()


# --- Task 4: client device -> order prefill ----------------------------------

def test_client_device_order_prefill(client_api, client_user):
    address = ClientAddress.objects.create(
        client=client_user, label="Uy", address_text="Chilonzor 9", lat="41.30000000", lng="69.24000000", is_default=True
    )
    device = ClientDevice.objects.create(client=client_user, name="Konditsioner", model="LG", address=address)

    response = client_api.post(reverse("client-device-order", args=[device.id]))

    assert response.status_code == 200
    data = response.data["data"]
    assert data["order_endpoint"] == "/api/v1/client/orders/"
    assert data["prefill"]["device"] == str(device.id)
    assert data["prefill"]["address"] == str(address.id)
    assert data["prefill"]["address_text"] == "Chilonzor 9"
    assert data["device"]["id"] == str(device.id)


# --- Task 1: Unfold order admin has usta/shogird inlines ---------------------

@pytest.fixture
def admin_web(django_admin_user):
    web = DjangoClient()
    web.force_login(django_admin_user)
    return web


def test_order_admin_changeform_has_usta_shogird_inlines(admin_web, client_user, service):
    order = Order.objects.create(
        client=client_user,
        service=service,
        address_text="Chilonzor",
        lat="41.30000000",
        lng="69.24000000",
        scheduled_date=date.today(),
        scheduled_time=time(10, 0),
    )

    response = admin_web.get(reverse("admin:orders_order_change", args=[order.id]))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Usta biriktirish" in html
    assert "Shogird biriktirish" in html
    # Inline formsets are wired (management form prefixes present).
    assert "assigned_masters-TOTAL_FORMS" in html
    assert "dashboard_assistants-TOTAL_FORMS" in html


# --- Task 2: Unfold cash-handover admin queue renders (per-row actions) ------

def test_order_admin_assign_page_renders_and_assigns(admin_web, client_user, service, master):
    order = _make_order(client_user, service)
    master2 = Master.objects.create(
        phone="+998900000333", first_name="Ikkinchi", last_name="Usta",
        approval_status=MasterApprovalStatus.APPROVED, is_active=True,
    )
    url = reverse("admin:orders_order_assign_row", args=[order.id])

    # GET renders the dashboard-style checkbox page (Bo'sh/Band + names).
    get = admin_web.get(url)
    assert get.status_code == 200
    html = get.content.decode()
    assert "Ali Usta" in html  # available master name (from conftest fixture)
    assert "Bo'sh" in html

    # POST assigns master as usta + master2 as shogird (unassigned -> assigned).
    post = admin_web.post(url, {"masters": [str(master.id)], "assistants": [str(master2.id)]})
    assert post.status_code == 302
    assert order.assigned_masters.filter(master=master, is_active=True).exists()
    assert order.dashboard_assistants.filter(assistant=master2, is_active=True).exists()

    # Re-assign (edit): replace usta with master2 only -> master deactivated.
    admin_web.post(url, {"masters": [str(master2.id)]})
    assert not order.assigned_masters.filter(master=master, is_active=True).exists()
    assert order.assigned_masters.filter(master=master2, is_active=True).exists()


def test_cash_handover_admin_changelist_renders(admin_web, master):
    MasterWallet.objects.create(master=master, balance_cash=200000)
    WithdrawRequest.objects.create(master=master, amount=200000, status=WithdrawRequest.PENDING)

    response = admin_web.get(reverse("admin:wallet_cashhandover_changelist"))

    assert response.status_code == 200
    html = response.content.decode()
    # Per-row action buttons are rendered.
    assert "Tasdiqlash" in html
