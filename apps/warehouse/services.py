from django.db import transaction
from rest_framework import serializers

from apps.warehouse.models import MasterInventory, StockMovement, WarehouseProduct


@transaction.atomic
def assign_inventory_to_master(*, master, product, quantity):
    """Move ``quantity`` of ``product`` from the central warehouse to a master's inventory.

    Single source of truth for "admin assigns product to master" — used by both the
    warehouse-admin API and the dashboard. Tops up the existing assignment (unique
    ``master`` + ``warehouse_product``), debits the central warehouse stock and records
    a ``StockMovement`` OUT. Row-locked + atomic so concurrent assigns can't oversell.

    Raises ``serializers.ValidationError`` if the warehouse lacks enough stock.
    Returns the updated :class:`MasterInventory` row.
    """
    product = WarehouseProduct.objects.select_for_update().get(pk=product.pk)
    if product.quantity < quantity:
        raise serializers.ValidationError({"quantity": "Omborda yetarli mahsulot yo'q"})

    item, _ = MasterInventory.objects.select_for_update().get_or_create(
        master=master,
        warehouse_product=product,
        defaults={
            "quantity": 0,
            "unit": product.unit,
            "low_threshold": product.low_threshold,
            "image": product.image,
        },
    )
    item.quantity += quantity
    item.save(update_fields=["quantity", "updated_at"])

    product.quantity -= quantity
    product.save(update_fields=["quantity", "updated_at"])

    StockMovement.objects.create(
        product=product,
        movement_type=StockMovement.OUT,
        quantity=quantity,
        master=master,
        note=f"Ustaga biriktirildi: {master}",
    )
    return item


@transaction.atomic
def return_inventory_to_warehouse(item):
    """Return a master's whole inventory row to the central warehouse, then delete it.

    Credits ``WarehouseProduct.quantity`` back and records a ``StockMovement`` IN,
    so deleting a master's assignment doesn't silently destroy stock. Locked + atomic.
    """
    product = WarehouseProduct.objects.select_for_update().get(pk=item.warehouse_product_id)
    returned = item.quantity
    product.quantity += returned
    product.save(update_fields=["quantity", "updated_at"])
    StockMovement.objects.create(
        product=product,
        movement_type=StockMovement.IN,
        quantity=returned,
        master=item.master,
        note=f"Ustadan qaytarildi: {item.master}",
    )
    item.delete()
    return returned


@transaction.atomic
def adjust_master_inventory(item, new_quantity):
    """Set a master's inventory row to ``new_quantity``, moving the delta to/from the
    central warehouse and recording a ``StockMovement``.

    delta > 0 debits the warehouse (OUT), delta < 0 returns stock (IN). Rejects a
    negative target and a debit the warehouse can't cover. Row-locked + atomic.
    """
    if new_quantity < 0:
        raise serializers.ValidationError({"quantity": "Miqdor manfiy bo'lishi mumkin emas"})
    product = WarehouseProduct.objects.select_for_update().get(pk=item.warehouse_product_id)
    item = MasterInventory.objects.select_for_update().get(pk=item.pk)
    delta = new_quantity - item.quantity
    if delta == 0:
        return item
    if delta > 0 and product.quantity < delta:
        raise serializers.ValidationError({"quantity": "Omborda yetarli mahsulot yo'q"})
    product.quantity -= delta
    product.save(update_fields=["quantity", "updated_at"])
    item.quantity = new_quantity
    item.save(update_fields=["quantity", "updated_at"])
    StockMovement.objects.create(
        product=product,
        movement_type=StockMovement.OUT if delta > 0 else StockMovement.IN,
        quantity=abs(delta),
        master=item.master,
        note=f"Usta biriktirish miqdori o'zgardi: {item.master}",
    )
    return item


def _move_product_quantity(product, delta):
    """Apply ``delta`` to a locked WarehouseProduct.quantity, guarding negative stock.

    Must run inside ``transaction.atomic()``. Records NO ledger row — callers decide
    whether/how to journal the movement.
    """
    product = WarehouseProduct.objects.select_for_update().get(pk=product.pk)
    new_qty = product.quantity + delta
    if new_qty < 0:
        raise serializers.ValidationError({"quantity": "Ombor qoldig'i manfiy bo'lishi mumkin emas"})
    product.quantity = new_qty
    product.save(update_fields=["quantity", "updated_at"])
    return product


@transaction.atomic
def adjust_warehouse_stock(product, delta, *, note="", master=None, movement_type=None):
    """Change central ``WarehouseProduct.quantity`` by ``delta`` and record a movement.

    delta > 0 = restock IN, delta < 0 = OUT. Single path that keeps the on-hand
    quantity and the ``StockMovement`` ledger in sync. Returns the created movement.
    Rejects a negative resulting stock. Row-locked + atomic.
    """
    product = _move_product_quantity(product, delta)
    return StockMovement.objects.create(
        product=product,
        movement_type=movement_type or (StockMovement.IN if delta >= 0 else StockMovement.OUT),
        quantity=abs(delta),
        master=master,
        note=note,
    )


@transaction.atomic
def apply_stock_movement_effect(product, movement_type, quantity):
    """Apply a manual StockMovement's effect to on-hand stock (IN adds, OUT removes).

    Used when the dashboard writes a raw StockMovement row directly — moves the
    stock so the ledger and quantity stay in sync (the caller saves the row itself).
    """
    delta = quantity if movement_type == StockMovement.IN else -quantity
    return _move_product_quantity(product, delta)


@transaction.atomic
def reverse_stock_movement(movement):
    """Undo a StockMovement's effect on on-hand stock (for delete). No new ledger row."""
    delta = -movement.quantity if movement.movement_type == StockMovement.IN else movement.quantity
    return _move_product_quantity(movement.product, delta)
