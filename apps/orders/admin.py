from django.contrib import admin

from apps.common.admin_mixins import HomeXModelAdmin, HomeXTabularInline
from apps.dashboard.models import DashboardOrderAssistant
from apps.orders.models import (
    HomeBanner,
    Order,
    OrderInventoryUsage,
    OrderMaster,
    OrderTracking,
    Review,
    ReviewPhoto,
)


@admin.register(HomeBanner)
class HomeBannerAdmin(HomeXModelAdmin):
    list_display = ("id", "banner_image", "banner_url", "is_active")
    list_editable = ("is_active",)
    search_fields = ("banner_url",)
    list_filter = ("is_active",)
    fields = ("banner_image", "banner_url", "is_active")


class OrderInventoryUsageInline(HomeXTabularInline):
    model = OrderInventoryUsage


class OrderMasterInline(HomeXTabularInline):
    """Usta biriktirish (dashboard 'Usta biriktirish' modalining admin ekvivalenti)."""

    model = OrderMaster
    fields = ("master", "has_accepted", "assigned_by", "is_active")
    autocomplete_fields = ("master",)
    extra = 0


class OrderAssistantInline(HomeXTabularInline):
    """Shogird biriktirish (dashboard 'Shogird biriktirish' modali)."""

    model = DashboardOrderAssistant
    fields = ("assistant", "assigned_by", "note", "is_active")
    autocomplete_fields = ("assistant",)
    extra = 0


@admin.register(Order)
class OrderAdmin(HomeXModelAdmin):
    list_display = (
        "id",
        "client",
        "master",
        "masters_count",
        "assistants_count",
        "service",
        "status",
        "payment_type",
        "total_amount",
        "scheduled_date",
    )
    search_fields = ("client__phone", "master__phone", "address_text", "note")
    list_filter = ("status", "payment_type", "scheduled_date")
    inlines = [OrderMasterInline, OrderAssistantInline, OrderInventoryUsageInline]

    @admin.display(description="Ustalar")
    def masters_count(self, obj):
        return obj.assigned_masters.filter(is_active=True).count()

    @admin.display(description="Shogirdlar")
    def assistants_count(self, obj):
        return obj.dashboard_assistants.filter(is_active=True).count()


@admin.register(OrderMaster)
class OrderMasterAdmin(HomeXModelAdmin):
    list_display = ("order", "master", "has_accepted", "is_active", "assigned_by", "created_at")
    search_fields = ("order__id", "master__phone", "master__first_name", "master__last_name")
    list_filter = ("has_accepted", "is_active")


@admin.register(OrderInventoryUsage)
class OrderInventoryUsageAdmin(HomeXModelAdmin):
    list_display = ("order", "inventory", "quantity", "unit_price", "total_price")


@admin.register(OrderTracking)
class OrderTrackingAdmin(HomeXModelAdmin):
    list_display = ("order", "master_lat", "master_lng", "distance_km", "eta_minutes", "updated_at")
    search_fields = ("order__client__phone", "order__master__phone", "order__address_text")


class ReviewPhotoInline(HomeXTabularInline):
    model = ReviewPhoto


@admin.register(Review)
class ReviewAdmin(HomeXModelAdmin):
    list_display = ("order", "master", "client", "rating", "is_official", "created_at")
    search_fields = ("comment", "master__phone", "client__phone")
    list_filter = ("rating", "is_official")
    inlines = [ReviewPhotoInline]


@admin.register(ReviewPhoto)
class ReviewPhotoAdmin(HomeXModelAdmin):
    list_display = ("review", "image")
