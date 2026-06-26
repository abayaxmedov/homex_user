from django.contrib import admin

from apps.common.admin_mixins import HomeXModelAdmin, HomeXTabularInline
from apps.services.models import Service, ServiceCategory, ServicePrice


class ServicePriceInline(HomeXTabularInline):
    model = ServicePrice


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(HomeXModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)


@admin.register(Service)
class ServiceAdmin(HomeXModelAdmin):
    list_display = ("name", "category", "base_price", "is_active")
    search_fields = ("name", "description")
    list_filter = ("category", "is_active")
    inlines = [ServicePriceInline]


@admin.register(ServicePrice)
class ServicePriceAdmin(HomeXModelAdmin):
    list_display = ("title", "service", "price", "unit", "is_active")
    search_fields = ("title", "service__name")
    list_filter = ("is_active",)
