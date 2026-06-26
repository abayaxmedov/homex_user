from django.contrib import admin

from apps.common.admin_mixins import HomeXModelAdmin, HomeXTabularInline
from apps.profiles.models import (
    ClientAddress,
    ClientDevice,
    MasterCertificate,
    MasterDocument,
    PrivacyPolicy,
    Tariff,
    TariffFeature,
)


@admin.register(ClientAddress)
class ClientAddressAdmin(HomeXModelAdmin):
    list_display = ("client", "label", "address_text", "is_default")
    search_fields = ("client__phone", "label", "address_text")
    list_filter = ("is_default",)


@admin.register(ClientDevice)
class ClientDeviceAdmin(HomeXModelAdmin):
    list_display = ("client", "name", "category", "address", "status", "created_at")
    search_fields = ("client__phone", "name", "model")
    list_filter = ("status", "category")


class TariffFeatureInline(HomeXTabularInline):
    model = TariffFeature
    fields = ("title", "sort_order")
    ordering = ("sort_order", "id")


@admin.register(TariffFeature)
class TariffFeatureAdmin(HomeXModelAdmin):
    list_display = ("title", "tariff", "sort_order")
    list_filter = ("tariff",)
    search_fields = ("title", "tariff__name")
    ordering = ("tariff__sort_order", "tariff__name", "sort_order", "id")


@admin.register(Tariff)
class TariffAdmin(HomeXModelAdmin):
    list_display = ("name", "price", "duration_days", "features_count", "is_popular", "is_active", "sort_order")
    search_fields = ("name",)
    list_filter = ("is_active", "is_popular")
    ordering = ("sort_order", "price", "name")
    inlines = (TariffFeatureInline,)

    @admin.display(description="Features")
    def features_count(self, obj):
        return obj.features.count()


@admin.register(MasterCertificate)
class MasterCertificateAdmin(HomeXModelAdmin):
    list_display = ("master", "title", "created_at")
    search_fields = ("master__phone", "title")


@admin.register(MasterDocument)
class MasterDocumentAdmin(HomeXModelAdmin):
    list_display = ("master", "title", "created_at")
    search_fields = ("master__phone", "title")


@admin.register(PrivacyPolicy)
class PrivacyPolicyAdmin(HomeXModelAdmin):
    list_display = ("version", "updated_at")
