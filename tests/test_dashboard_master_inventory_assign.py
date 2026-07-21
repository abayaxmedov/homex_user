from django.urls import reverse

from apps.accounts.models import Master
from apps.warehouse.models import MasterInventory, StockMovement, WarehouseProduct


def _assign(admin_api, master, product, quantity):
    return admin_api.post(
        reverse("dashboard-master-inventory"),
        {"master": str(master.id), "warehouse_product": str(product.id), "quantity": str(quantity)},
        format="json",
    )


def test_dashboard_assign_deducts_warehouse_and_records_movement(admin_api, master):
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=10, sale_price=15000)

    response = _assign(admin_api, master, product, 3)

    assert response.status_code == 201
    product.refresh_from_db()
    assert product.quantity == 7  # 10 - 3, markaziy ombordan ayirildi
    item = MasterInventory.objects.get(master=master, warehouse_product=product)
    assert item.quantity == 3
    # Audit izi yozildi.
    assert StockMovement.objects.filter(
        product=product, master=master, movement_type=StockMovement.OUT, quantity=3
    ).count() == 1


def test_dashboard_assign_twice_tops_up_existing(admin_api, master):
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=10, sale_price=15000)

    first = _assign(admin_api, master, product, 3)
    second = _assign(admin_api, master, product, 4)  # xuddi shu master+product

    assert first.status_code == 201
    assert second.status_code == 201  # 400 emas — miqdor ustiga qo'shiladi
    item = MasterInventory.objects.get(master=master, warehouse_product=product)
    assert item.quantity == 7  # 3 + 4
    product.refresh_from_db()
    assert product.quantity == 3  # 10 - 3 - 4
    assert MasterInventory.objects.filter(master=master, warehouse_product=product).count() == 1


def test_dashboard_assign_more_than_warehouse_is_rejected(admin_api, master):
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=5, sale_price=15000)

    response = _assign(admin_api, master, product, 999)

    assert response.status_code == 400
    product.refresh_from_db()
    assert product.quantity == 5  # o'zgarmadi
    assert not MasterInventory.objects.filter(master=master).exists()
    assert not StockMovement.objects.exists()


def test_dashboard_assign_second_master_gets_own_row(admin_api, master):
    other = Master.objects.create(phone="+998900000042", first_name="Vali", last_name="Usta")
    product = WarehouseProduct.objects.create(name="Filter", unit="dona", quantity=10, sale_price=15000)

    assert _assign(admin_api, master, product, 2).status_code == 201
    assert _assign(admin_api, other, product, 3).status_code == 201

    product.refresh_from_db()
    assert product.quantity == 5  # 10 - 2 - 3
    assert MasterInventory.objects.filter(warehouse_product=product).count() == 2
