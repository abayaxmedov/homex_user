from django.contrib import admin

from apps.common.admin_mixins import HomeXModelAdmin, HomeXTabularInline
from apps.market.models import MarketCategory, MarketFavorite, MarketOrder, MarketProduct, MarketProductImage


class MarketProductImageInline(HomeXTabularInline):
    model = MarketProductImage


@admin.register(MarketCategory)
class MarketCategoryAdmin(HomeXModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(MarketProduct)
class MarketProductAdmin(HomeXModelAdmin):
    list_display = ("name", "category", "seller", "condition", "price", "quantity", "is_active", "is_moderated")
    search_fields = ("name", "description", "seller__phone")
    list_filter = ("condition", "is_active", "is_moderated")
    inlines = [MarketProductImageInline]


@admin.register(MarketProductImage)
class MarketProductImageAdmin(HomeXModelAdmin):
    list_display = ("product", "image")


@admin.register(MarketFavorite)
class MarketFavoriteAdmin(HomeXModelAdmin):
    list_display = ("client", "product", "created_at")
    search_fields = ("client__phone", "product__name")


@admin.register(MarketOrder)
class MarketOrderAdmin(HomeXModelAdmin):
    list_display = ("client", "product", "quantity", "total_amount", "status", "created_at")
    search_fields = ("client__phone", "product__name", "delivery_address")
    list_filter = ("status",)
