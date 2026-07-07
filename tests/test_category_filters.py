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
from apps.warehouse.models import MasterInventory, WarehouseCategory, WarehouseProduct


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
    order = Order.objects.create(
        client=client_user,
        master=master,
        service=service,
        address_text="Chilonzor 12",
        lat=Decimal("41.30000000"),
        lng=Decimal("69.24000000"),
        scheduled_date=timezone.localdate(),
        scheduled_time=time(10, 0),
    )
    if master is not None:
        # Masters now only see orders the admin assigned to them.
        from apps.orders.models import OrderMaster

        OrderMaster.objects.create(order=order, master=master, has_accepted=True)
    return order


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


# --- Warehouse (ombor) category ----------------------------------------------

@pytest.fixture
def warehouse_setup(db):
    cat_a = WarehouseCategory.objects.create(name="Kabellar", slug="kabellar")
    cat_b = WarehouseCategory.objects.create(name="Asboblar", slug="asboblar")
    prod_a = WarehouseProduct.objects.create(category=cat_a, name="Kabel 2x1.5", quantity=100)
    prod_b = WarehouseProduct.objects.create(category=cat_b, name="Perforator", quantity=10)
    return {"cat_a": cat_a, "cat_b": cat_b, "prod_a": prod_a, "prod_b": prod_b}


def test_admin_warehouse_category_list(admin_api, warehouse_setup):
    response = admin_api.get(reverse("admin-warehouse-categories"))
    assert response.status_code == 200
    by_slug = {c["slug"]: c for c in rows(response)}
    assert {"kabellar", "asboblar"} <= set(by_slug)
    assert by_slug["kabellar"]["products_count"] == 1


def test_admin_warehouse_products_filter_by_category(admin_api, warehouse_setup):
    response = admin_api.get(reverse("admin-warehouse-products"), {"category": "kabellar"})
    assert response.status_code == 200
    assert {str(row["id"]) for row in rows(response)} == {str(warehouse_setup["prod_a"].id)}


def test_dashboard_warehouse_category_list(admin_api, warehouse_setup):
    response = admin_api.get(reverse("dashboard-warehouse-categories"))
    assert response.status_code == 200
    assert {"kabellar", "asboblar"} <= {c["slug"] for c in rows(response)}


def test_dashboard_warehouse_products_filter_by_category(admin_api, warehouse_setup):
    response = admin_api.get(reverse("dashboard-warehouse-products"), {"category": str(warehouse_setup["cat_b"].id)})
    assert response.status_code == 200
    result = rows(response)
    assert {str(row["id"]) for row in result} == {str(warehouse_setup["prod_b"].id)}
    # price fields exposed (Figma: Tannarx / Sotuv narxi columns)
    row = result[0]
    assert {"cost_price", "sale_price", "stock_value"} <= set(row)


def test_dashboard_warehouse_stats_total_value(admin_api, warehouse_setup):
    product = warehouse_setup["prod_a"]  # quantity 100
    product.cost_price = 1000
    product.save(update_fields=["cost_price"])

    response = admin_api.get(reverse("dashboard-warehouse-stats"))
    assert response.status_code == 200
    data = response.data["data"]
    assert float(data["total_value"]) == 100 * 1000  # prod_a only; prod_b cost 0


def test_master_inventory_filter_by_category(master_api, master, warehouse_setup):
    MasterInventory.objects.create(master=master, warehouse_product=warehouse_setup["prod_a"], quantity=5)
    MasterInventory.objects.create(master=master, warehouse_product=warehouse_setup["prod_b"], quantity=3)

    response = master_api.get(reverse("master-inventory"), {"category": "asboblar"})
    assert response.status_code == 200
    assert {row["product_name"] for row in rows(response)} == {"Perforator"}
