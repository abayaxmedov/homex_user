"""Regression tests for the category list APIs and `?category` filters.

Covers the service-order (Order.service.category) and market-order
(MarketOrder.product.category) filters added across the client, master,
dashboard and internal audiences, plus the shared ``filter_by_category``
helper semantics (id, slug and the ``all``/``hammasi`` sentinels).
"""
from datetime import time
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.market.models import MarketCategory, MarketOrder, MarketProduct
from apps.orders.models import Order
from apps.services.models import Service, ServiceCategory


def rows(response):
    """Extract the list rows from either envelope shape (paginated vs plain)."""
    body = response.data
    return body["results"] if "results" in body else body["data"]


@pytest.fixture
def service_categories(db):
    cat_a = ServiceCategory.objects.create(name="Elektrik", slug="elektrik")
    cat_b = ServiceCategory.objects.create(name="Santexnik", slug="santexnik")
    svc_a = Service.objects.create(category=cat_a, name="Rozetka", base_price=50000)
    svc_b = Service.objects.create(category=cat_b, name="Truba", base_price=70000)
    return {"cat_a": cat_a, "cat_b": cat_b, "svc_a": svc_a, "svc_b": svc_b}


def make_order(client_user, service, master=None):
    return Order.objects.create(
        client=client_user,
        master=master,
        service=service,
        address_text="Chilonzor 12",
        lat=Decimal("41.30000000"),
        lng=Decimal("69.24000000"),
        scheduled_date=timezone.localdate(),
        scheduled_time=time(10, 0),
    )


@pytest.fixture
def market_setup(db, client_user):
    cat_a = MarketCategory.objects.create(name="Asboblar", slug="asboblar")
    cat_b = MarketCategory.objects.create(name="Mebel", slug="mebel")
    prod_a = MarketProduct.objects.create(category=cat_a, name="Drel", price=Decimal("300000"), quantity=5)
    prod_b = MarketProduct.objects.create(category=cat_b, name="Stul", price=Decimal("150000"), quantity=5)
    order_a = MarketOrder.objects.create(client=client_user, product=prod_a, quantity=1, delivery_address="A", phone="+998900000001")
    order_b = MarketOrder.objects.create(client=client_user, product=prod_b, quantity=1, delivery_address="B", phone="+998900000002")
    return {"cat_a": cat_a, "cat_b": cat_b, "order_a": order_a, "order_b": order_b}


# --- Client service orders --------------------------------------------------

def test_client_orders_filter_by_category_id(client_api, client_user, service_categories):
    make_order(client_user, service_categories["svc_a"])
    make_order(client_user, service_categories["svc_b"])

    response = client_api.get(reverse("client-orders"), {"category": str(service_categories["cat_a"].id)})
    assert response.status_code == 200
    services = {str(row["service"]) for row in rows(response)}
    assert services == {str(service_categories["svc_a"].id)}


def test_client_orders_filter_by_category_slug(client_api, client_user, service_categories):
    make_order(client_user, service_categories["svc_a"])
    make_order(client_user, service_categories["svc_b"])

    response = client_api.get(reverse("client-orders"), {"category": "santexnik"})
    assert response.status_code == 200
    assert {str(row["service"]) for row in rows(response)} == {str(service_categories["svc_b"].id)}


def test_client_orders_all_sentinel_returns_everything(client_api, client_user, service_categories):
    make_order(client_user, service_categories["svc_a"])
    make_order(client_user, service_categories["svc_b"])

    response = client_api.get(reverse("client-orders"), {"category": "all"})
    assert response.status_code == 200
    assert len(rows(response)) == 2


# --- Master service orders ---------------------------------------------------

def test_master_orders_filter_by_category(master_api, master, client_user, service_categories):
    make_order(client_user, service_categories["svc_a"], master=master)
    make_order(client_user, service_categories["svc_b"], master=master)

    response = master_api.get(reverse("master-orders"), {"category": "elektrik"})
    assert response.status_code == 200
    assert {str(row["service"]) for row in rows(response)} == {str(service_categories["svc_a"].id)}


# --- Client market orders ----------------------------------------------------

def test_client_market_orders_filter_by_category(client_api, market_setup):
    response = client_api.get(reverse("client-market-orders"), {"category": str(market_setup["cat_a"].id)})
    assert response.status_code == 200
    ids = {str(row["id"]) for row in rows(response)}
    assert ids == {str(market_setup["order_a"].id)}

    response = client_api.get(reverse("client-market-orders"), {"category": "mebel"})
    assert {str(row["id"]) for row in rows(response)} == {str(market_setup["order_b"].id)}


# --- Dashboard ---------------------------------------------------------------

def test_dashboard_orders_filter_by_category(admin_api, client_user, service_categories):
    make_order(client_user, service_categories["svc_a"])
    make_order(client_user, service_categories["svc_b"])

    response = admin_api.get(reverse("dashboard-orders"), {"category": str(service_categories["cat_b"].id)})
    assert response.status_code == 200
    assert {str(row["service"]) for row in rows(response)} == {str(service_categories["svc_b"].id)}


def test_dashboard_market_orders_filter_by_category(admin_api, market_setup):
    response = admin_api.get(reverse("dashboard-market-orders"), {"category": "asboblar"})
    assert response.status_code == 200
    assert {str(row["id"]) for row in rows(response)} == {str(market_setup["order_a"].id)}


# --- Client services category list (?category + ?search) ---------------------

def test_client_services_category_filter_returns_single(client_api, service_categories):
    response = client_api.get(reverse("client-services"), {"category": "elektrik"})
    assert response.status_code == 200
    result = rows(response)
    assert {c["slug"] for c in result} == {"elektrik"}


def test_client_services_search(client_api, service_categories):
    response = client_api.get(reverse("client-services"), {"search": "santex"})
    assert response.status_code == 200
    assert {c["slug"] for c in rows(response)} == {"santexnik"}
