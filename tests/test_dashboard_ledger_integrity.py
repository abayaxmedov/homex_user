from decimal import Decimal

from django.urls import reverse

from apps.warehouse.models import MasterInventory, StockMovement, WarehouseProduct
from apps.warehouse.services import assign_inventory_to_master
from apps.wallet.models import MasterWallet, WalletTransaction


def _product(quantity=10):
    return WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=quantity, sale_price=15000)


# --- C1: master-inventory DELETE returns stock ---

def test_master_inventory_delete_returns_stock(admin_api, master):
    product = _product(10)
    item = assign_inventory_to_master(master=master, product=product, quantity=4)  # warehouse -> 6
    product.refresh_from_db()
    assert product.quantity == 6

    resp = admin_api.delete(reverse("dashboard-master-inventory-detail", args=[item.id]))
    assert resp.status_code in (200, 204)
    product.refresh_from_db()
    assert product.quantity == 10  # 4 returned
    assert not MasterInventory.objects.filter(id=item.id).exists()
    assert StockMovement.objects.filter(product=product, movement_type=StockMovement.IN, quantity=4).exists()


def test_master_inventory_delete_used_item_returns_stock_not_500(admin_api, master, client_user, service):
    # An item used in a past order is PROTECT-referenced by OrderInventoryUsage — deleting it
    # must return the stock and soft-remove (zero) it, NOT raise a 500 (ProtectedError).
    from datetime import date, time

    from apps.orders.models import Order, OrderInventoryUsage, OrderStatus

    product = _product(10)
    item = assign_inventory_to_master(master=master, product=product, quantity=4)  # warehouse -> 6
    order = Order.objects.create(
        client=client_user, master=master, service=service,
        address_text="X", lat="41.30000000", lng="69.25000000",
        scheduled_date=date.today(), scheduled_time=time(10, 0), status=OrderStatus.COMPLETED,
    )
    OrderInventoryUsage.objects.create(order=order, inventory=item, quantity=3, unit_price=15000)

    resp = admin_api.delete(reverse("dashboard-master-inventory-detail", args=[item.id]))
    assert resp.status_code in (200, 204)  # not 500

    item.refresh_from_db()  # still exists (history preserved) but zeroed -> hidden from master
    assert item.quantity == 0
    product.refresh_from_db()
    assert product.quantity == 10  # 4 returned to the central warehouse (6 -> 10)
    assert StockMovement.objects.filter(product=product, movement_type=StockMovement.IN, quantity=4).exists()


# --- C2: master-inventory PATCH quantity moves warehouse ---

def test_master_inventory_patch_quantity_moves_warehouse(admin_api, master):
    product = _product(10)
    item = assign_inventory_to_master(master=master, product=product, quantity=3)  # warehouse -> 7

    resp = admin_api.patch(
        reverse("dashboard-master-inventory-detail", args=[item.id]), {"quantity": "5"}, format="json"
    )
    assert resp.status_code == 200
    item.refresh_from_db()
    product.refresh_from_db()
    assert item.quantity == 5
    assert product.quantity == 5  # 2 more taken from warehouse (7 -> 5)
    assert StockMovement.objects.filter(product=product, movement_type=StockMovement.OUT, quantity=2).exists()


# --- C3: warehouse product create/update journals stock ---

def test_warehouse_product_create_records_opening_movement(admin_api):
    resp = admin_api.post(
        reverse("dashboard-warehouse-products"),
        {"name": "Kabel", "unit": "dona", "quantity": "12", "sale_price": "5000"},
        format="json",
    )
    assert resp.status_code == 201
    product = WarehouseProduct.objects.get(name="Kabel")
    assert product.quantity == 12
    assert StockMovement.objects.filter(product=product, movement_type=StockMovement.IN, quantity=12).exists()


def test_warehouse_product_patch_quantity_records_movement(admin_api):
    product = _product(10)
    resp = admin_api.patch(
        reverse("dashboard-warehouse-product-detail", args=[product.id]), {"quantity": "25"}, format="json"
    )
    assert resp.status_code == 200
    product.refresh_from_db()
    assert product.quantity == 25
    assert StockMovement.objects.filter(product=product, movement_type=StockMovement.IN, quantity=15).exists()


# --- C4: stock movement POST moves stock; DELETE reverses ---

def test_stock_movement_post_moves_stock(admin_api):
    product = _product(10)
    resp = admin_api.post(
        reverse("dashboard-stock-movements"),
        {"product": str(product.id), "movement_type": "kirim", "quantity": "5", "note": "qo'shildi"},
        format="json",
    )
    assert resp.status_code == 201
    product.refresh_from_db()
    assert product.quantity == 15  # IN applied

    movement_id = resp.data["data"]["id"]
    delete = admin_api.delete(reverse("dashboard-stock-movement-detail", args=[movement_id]))
    assert delete.status_code in (200, 204)
    product.refresh_from_db()
    assert product.quantity == 10  # reversed


# --- C5: wallet transaction POST moves balance; edit financial field blocked; DELETE reverses ---

def test_wallet_transaction_post_moves_balance(admin_api, master):
    resp = admin_api.post(
        reverse("dashboard-wallet-transactions"),
        {
            "master": str(master.id),
            "transaction_type": "kirim",
            "amount": "50000",
            "description": "bonus",
            "payment_method": "cash",
        },
        format="json",
    )
    assert resp.status_code == 201
    wallet = MasterWallet.objects.get(master=master)
    assert wallet.balance_cash == Decimal("50000")

    txn_id = resp.data["data"]["id"]
    # Financial field edit is blocked.
    bad = admin_api.patch(
        reverse("dashboard-wallet-transaction-detail", args=[txn_id]), {"amount": "999"}, format="json"
    )
    assert bad.status_code == 400
    # Delete reverses the balance.
    admin_api.delete(reverse("dashboard-wallet-transaction-detail", args=[txn_id]))
    wallet.refresh_from_db()
    assert wallet.balance_cash == Decimal("0")


# --- C6: withdraw delete guard + wallet balances read-only ---

def test_cannot_delete_approved_withdraw(admin_api, master):
    from apps.wallet.models import WithdrawRequest

    wallet, _ = MasterWallet.objects.get_or_create(master=master)
    wallet.balance_cash = Decimal("300000")
    wallet.save(update_fields=["balance_cash"])
    wr = WithdrawRequest.objects.create(master=master, amount=Decimal("100000"), status=WithdrawRequest.APPROVED)

    resp = admin_api.delete(reverse("dashboard-withdraw-request-detail", args=[wr.id]))
    assert resp.status_code == 400
    assert WithdrawRequest.objects.filter(id=wr.id).exists()
