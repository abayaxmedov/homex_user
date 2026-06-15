from django.contrib import admin

from apps.services.models import Service, ServiceCategory, ServicePrice


class ServicePriceInline(admin.TabularInline):
    model = ServicePrice
    extra = 0


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    search_fields = ("name", "slug")
    list_filter = ("is_active",)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "base_price", "is_active")
    search_fields = ("name", "description")
    list_filter = ("category", "is_active")
    inlines = [ServicePriceInline]


@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = ("title", "service", "price", "unit", "is_active")
    search_fields = ("title", "service__name")
    list_filter = ("is_active",)
