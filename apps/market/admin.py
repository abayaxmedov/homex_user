from django.contrib import admin

from apps.market.models import MarketCategory, MarketFavorite, MarketOrder, MarketProduct, MarketProductImage


class MarketProductImageInline(admin.TabularInline):
    model = MarketProductImage
    extra = 0


@admin.register(MarketCategory)
class MarketCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")


@admin.register(MarketProduct)
class MarketProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "seller", "condition", "price", "quantity", "is_active", "is_moderated")
    search_fields = ("name", "description", "seller__phone")
    list_filter = ("condition", "is_active", "is_moderated")
    inlines = [MarketProductImageInline]


@admin.register(MarketProductImage)
class MarketProductImageAdmin(admin.ModelAdmin):
    list_display = ("product", "image")


@admin.register(MarketFavorite)
class MarketFavoriteAdmin(admin.ModelAdmin):
    list_display = ("client", "product", "created_at")
    search_fields = ("client__phone", "product__name")


@admin.register(MarketOrder)
class MarketOrderAdmin(admin.ModelAdmin):
    list_display = ("client", "product", "quantity", "total_amount", "status", "created_at")
    search_fields = ("client__phone", "product__name", "delivery_address")
    list_filter = ("status",)
