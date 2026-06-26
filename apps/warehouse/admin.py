from django.contrib import admin

from apps.common.admin_mixins import HomeXModelAdmin
from apps.warehouse.models import MasterInventory, StockMovement, WarehouseProduct


@admin.register(WarehouseProduct)
class WarehouseProductAdmin(HomeXModelAdmin):
    list_display = ("name", "unit", "quantity", "low_threshold", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active", "unit")


@admin.register(StockMovement)
class StockMovementAdmin(HomeXModelAdmin):
    list_display = ("product", "movement_type", "quantity", "master", "created_at")
    search_fields = ("product__name", "note", "master__phone")
    list_filter = ("movement_type",)


@admin.register(MasterInventory)
class MasterInventoryAdmin(HomeXModelAdmin):
    list_display = ("master", "warehouse_product", "quantity", "unit", "low_threshold", "assigned_at")
    search_fields = ("master__phone", "warehouse_product__name")
    list_filter = ("unit",)
