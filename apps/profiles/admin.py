from django.contrib import admin

from apps.profiles.models import (
    ClientAddress,
    ClientDevice,
    MasterCertificate,
    MasterDocument,
    PrivacyPolicy,
    Tariff,
)


@admin.register(ClientAddress)
class ClientAddressAdmin(admin.ModelAdmin):
    list_display = ("client", "label", "address_text", "is_default")
    search_fields = ("client__phone", "label", "address_text")
    list_filter = ("is_default",)


@admin.register(ClientDevice)
class ClientDeviceAdmin(admin.ModelAdmin):
    list_display = ("client", "name", "category", "address", "status", "created_at")
    search_fields = ("client__phone", "name", "model")
    list_filter = ("status", "category")


@admin.register(Tariff)
class TariffAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "duration_days", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(MasterCertificate)
class MasterCertificateAdmin(admin.ModelAdmin):
    list_display = ("master", "title", "created_at")
    search_fields = ("master__phone", "title")


@admin.register(MasterDocument)
class MasterDocumentAdmin(admin.ModelAdmin):
    list_display = ("master", "title", "created_at")
    search_fields = ("master__phone", "title")


@admin.register(PrivacyPolicy)
class PrivacyPolicyAdmin(admin.ModelAdmin):
    list_display = ("version", "updated_at")
