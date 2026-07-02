from django.contrib import admin

from apps.common.admin_mixins import HomeXModelAdmin, HomeXTabularInline
from apps.orders.models import HomeBanner, Order, OrderInventoryUsage, OrderTracking, Review, ReviewPhoto


@admin.register(HomeBanner)
class HomeBannerAdmin(HomeXModelAdmin):
    list_display = ("id", "banner_image", "banner_url", "is_active")
    list_editable = ("is_active",)
    search_fields = ("banner_url",)
    list_filter = ("is_active",)
    fields = ("banner_image", "banner_url", "is_active")


class OrderInventoryUsageInline(HomeXTabularInline):
    model = OrderInventoryUsage


@admin.register(Order)
class OrderAdmin(HomeXModelAdmin):
    list_display = (
        "id",
        "client",
        "master",
        "service",
        "status",
        "payment_type",
        "total_amount",
        "before_photo",
        "completion_photo",
        "receipt_approved_at",
        "scheduled_date",
    )
    search_fields = ("client__phone", "master__phone", "address_text", "note")
    list_filter = ("status", "payment_type", "scheduled_date")
    inlines = [OrderInventoryUsageInline]


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
