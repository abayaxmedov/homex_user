from datetime import date, time

from django.urls import reverse

from apps.orders.models import Order, OrderStatus
from apps.warehouse.models import MasterInventory, StockMovement, WarehouseProduct
from apps.wallet.models import MasterExpense, MasterWallet, WalletTransaction, WithdrawRequest


def test_master_wallet_transactions_withdraw_and_expenses(master_api, master):
    wallet = MasterWallet.objects.create(master=master, balance_cash=100000, balance_online=50000)
    WalletTransaction.objects.create(
        master=master,
        transaction_type=WalletTransaction.IN,
        amount=100000,
        description="Service",
        payment_method=WalletTransaction.CASH,
    )

    wallet_response = master_api.get(reverse("master-wallet"))
    transactions = master_api.get(reverse("master-wallet-transactions"))
    withdraw = master_api.post(reverse("master-wallet-withdraw"), {"amount": "50000"}, format="json")
    expense = master_api.post(
        reverse("master-expenses"),
        {"purpose": "Yo'l haqi", "name": "Taxi", "amount": "20000", "date": str(date.today())},
        format="json",
    )

    assert wallet_response.status_code == 200
    assert wallet_response.data["data"]["balance_cash"] == "100000.00"
    assert transactions.status_code == 200
    assert withdraw.status_code == 201
    assert expense.status_code == 201
    assert WithdrawRequest.objects.filter(master=master, amount=50000).exists()
    assert MasterExpense.objects.filter(master=master, name="Taxi").exists()
    assert wallet.balance_online == 50000


def test_admin_inventory_urls_match_tz_and_restore_stock(admin_api, master):
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=10)

    assign = admin_api.post(
        reverse("admin-master-inventory", args=[master.id]),
        {"warehouse_product_id": str(product.id), "quantity": "4"},
        format="json",
    )
    item = MasterInventory.objects.get(master=master, warehouse_product=product)
    update = admin_api.put(
        reverse("admin-master-inventory-detail", args=[master.id, item.id]),
        {"quantity": "2"},
        format="json",
    )
    delete = admin_api.delete(reverse("admin-master-inventory-detail", args=[master.id, item.id]))
    product.refresh_from_db()

    assert assign.status_code == 201
    assert update.status_code == 200
    assert delete.status_code == 204
    assert product.quantity == 10
    assert StockMovement.objects.filter(product=product, movement_type=StockMovement.IN).exists()


def test_master_and_client_order_api_flow(client_api, master_api, master, client_user, service):
    order_response = client_api.post(
        reverse("client-orders"),
        {
            "master": str(master.id),
            "service": str(service.id),
            "address_text": "Tashkent",
            "lat": "41.30000000",
            "lng": "69.25000000",
            "scheduled_date": str(date.today()),
            "scheduled_time": "10:00",
            "payment_type": "cash",
        },
        format="json",
    )
    order = Order.objects.get(client=client_user)
    from apps.orders.models import OrderMaster

    OrderMaster.objects.create(order=order, master=master)  # admin assigns the master

    list_response = master_api.get(reverse("master-orders"))
    accept_response = master_api.post(reverse("master-order-accept", args=[order.id]))
    order.refresh_from_db()
    order.status = OrderStatus.COMPLETED
    order.save(update_fields=["status"])
    rate_response = client_api.post(
        reverse("client-order-rate", args=[order.id]),
        {"rating": 5, "comment": "Zo'r"},
        format="json",
    )
    pay_response = client_api.post(
        reverse("client-order-pay", args=[order.id]),
        {"payment_method": "online", "bonus_used": "0"},
        format="json",
    )

    assert order_response.status_code == 201
    assert list_response.status_code == 200
    assert accept_response.status_code == 200
    assert rate_response.status_code == 201
    assert pay_response.status_code == 200
    assert "payment_url" in pay_response.data["data"]
