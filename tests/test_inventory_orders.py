import json
from datetime import date, time
from uuid import uuid4

from django.urls import reverse

from apps.orders.models import Order, OrderStatus, PaymentType
from apps.orders.receipts import receipt_rows
from apps.orders.serializers import OrderCompleteSerializer
from apps.warehouse.models import MasterInventory, StockMovement, WarehouseProduct
from apps.warehouse.serializers import AdminAssignInventorySerializer
from apps.wallet.models import MasterWallet, WalletTransaction


def test_assign_inventory_decreases_warehouse(master):
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=10)
    serializer = AdminAssignInventorySerializer(
        data={"warehouse_product_id": product.id, "quantity": "3"},
        context={"master": master},
    )
    assert serializer.is_valid(), serializer.errors
    item = serializer.save()
    product.refresh_from_db()

    assert item.quantity == 3
    assert product.quantity == 7
    assert StockMovement.objects.filter(product=product, movement_type=StockMovement.OUT).exists()


def test_order_complete_updates_wallet_and_inventory(master, client_user, service):
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=10, sale_price=15000)
    item = MasterInventory.objects.create(master=master, warehouse_product=product, quantity=5, unit="dona")
    order = Order.objects.create(
        client=client_user,
        master=master,
        service=service,
        address_text="Tashkent",
        lat="41.30000000",
        lng="69.25000000",
        scheduled_date=date.today(),
        scheduled_time=time(10, 0),
        status=OrderStatus.ACCEPTED,
        payment_type=PaymentType.ONLINE,
    )
    serializer = OrderCompleteSerializer(
        data={
            "service_fee": "100000",
            "used_items": [{"inventory_id": str(item.id), "quantity": 2, "unit_price": 999999}],
        },
        context={"order": order},
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    item.refresh_from_db()
    order.refresh_from_db()
    wallet = MasterWallet.objects.get(master=master)
    usage = order.inventory_usages.get()

    assert item.quantity == 3
    assert usage.unit_price == 15000
    assert usage.total_price == 30000
    assert order.inventory_total == 30000
    assert order.total_amount == 130000
    assert wallet.balance_online == 130000
    assert WalletTransaction.objects.filter(
        master=master,
        amount=130000,
        payment_method=WalletTransaction.ONLINE,
    ).exists()
    rows = receipt_rows(order)
    assert any("Filter; miqdor: 2" in str(value) and "15,000.00" in str(value) for _, value in rows)


def test_order_complete_accepts_multipart_used_items_json_string(master, client_user, service):
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=10, sale_price=15000)
    item = MasterInventory.objects.create(master=master, warehouse_product=product, quantity=5, unit="dona")
    order = Order.objects.create(
        client=client_user,
        master=master,
        service=service,
        address_text="Tashkent",
        lat="41.30000000",
        lng="69.25000000",
        scheduled_date=date.today(),
        scheduled_time=time(10, 0),
        status=OrderStatus.ACCEPTED,
    )
    serializer = OrderCompleteSerializer(
        data={
            "service_fee": "100000",
            "used_items": json.dumps([{"inventory_id": str(item.id), "quantity": "2.00"}]),
        },
        context={"order": order},
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    item.refresh_from_db()
    order.refresh_from_db()

    assert item.quantity == 3
    assert order.inventory_total == 30000


def test_master_inventory_use_updates_order_totals(master_api, master, client_user, service):
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=10, sale_price=15000)
    item = MasterInventory.objects.create(master=master, warehouse_product=product, quantity=5, unit="dona")
    order = Order.objects.create(
        client=client_user,
        master=master,
        service=service,
        address_text="Tashkent",
        lat="41.30000000",
        lng="69.25000000",
        scheduled_date=date.today(),
        scheduled_time=time(10, 0),
        status=OrderStatus.ACCEPTED,
        service_fee=100000,
        total_amount=100000,
    )

    response = master_api.post(
        reverse("master-inventory-use", args=[item.id]),
        {"quantity": "2", "order_id": str(order.id)},
        format="json",
    )
    item.refresh_from_db()
    order.refresh_from_db()
    usage = order.inventory_usages.get()

    assert response.status_code == 200
    assert response.data["data"]["sale_price"] == "15000.00"
    assert item.quantity == 3
    assert usage.unit_price == 15000
    assert usage.total_price == 30000
    assert order.inventory_total == 30000
    assert order.total_amount == 130000


def test_master_inventory_use_invalid_order_does_not_decrease_inventory(master_api, master):
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=10, sale_price=15000)
    item = MasterInventory.objects.create(master=master, warehouse_product=product, quantity=5, unit="dona")

    response = master_api.post(
        reverse("master-inventory-use", args=[item.id]),
        {"quantity": "2", "order_id": str(uuid4())},
        format="json",
    )
    item.refresh_from_db()

    assert response.status_code == 404
    assert item.quantity == 5
