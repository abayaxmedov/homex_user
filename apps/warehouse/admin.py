from django.contrib import admin

from apps.common.admin_mixins import HomeXModelAdmin
from apps.warehouse.models import MasterInventory, StockMovement, WarehouseCategory, WarehouseProduct


@admin.register(WarehouseCategory)
class WarehouseCategoryAdmin(HomeXModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(WarehouseProduct)
class WarehouseProductAdmin(HomeXModelAdmin):
    list_display = ("name", "category", "unit", "quantity", "cost_price", "sale_price", "low_threshold", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active", "unit", "category")


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
