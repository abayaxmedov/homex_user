from datetime import date, time

from apps.orders.models import Order, OrderStatus, PaymentType
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
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=10)
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
            "used_items": [{"inventory_id": str(item.id), "quantity": 2, "unit_price": 15000}],
        },
        context={"order": order},
    )
    assert serializer.is_valid(), serializer.errors
    serializer.save()
    item.refresh_from_db()
    wallet = MasterWallet.objects.get(master=master)

    assert item.quantity == 3
    assert wallet.balance_online == 130000
    assert WalletTransaction.objects.filter(
        master=master,
        amount=130000,
        payment_method=WalletTransaction.ONLINE,
    ).exists()
