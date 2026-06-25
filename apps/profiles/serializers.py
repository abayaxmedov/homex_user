from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.profiles.models import (
    ClientAddress,
    ClientDevice,
    MasterCertificate,
    MasterDocument,
    PrivacyPolicy,
    Tariff,
)
from apps.services.serializers import ServiceCategorySerializer


class ClientAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientAddress
        fields = ("id", "label", "address_text", "lat", "lng", "is_default", "created_at")
        read_only_fields = ("id", "created_at")


class ClientDeviceSerializer(serializers.ModelSerializer):
    category_detail = ServiceCategorySerializer(source="category", read_only=True)
    address_detail = ClientAddressSerializer(source="address", read_only=True)
    order_count = serializers.SerializerMethodField()
    last_order = serializers.SerializerMethodField()

    class Meta:
        model = ClientDevice
        fields = (
            "id",
            "name",
            "category",
            "category_detail",
            "model",
            "image",
            "address",
            "address_detail",
            "status",
            "order_count",
            "last_order",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    @extend_schema_field(serializers.IntegerField)
    def get_order_count(self, obj):
        from apps.orders.models import Order

        return Order.objects.filter(client=obj.client, address=obj.address, service__category=obj.category).count()

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_last_order(self, obj):
        from apps.orders.models import Order

        order = (
            Order.objects.filter(client=obj.client, address=obj.address, service__category=obj.category)
            .order_by("-created_at")
            .first()
        )
        if not order:
            return None
        return {
            "id": order.id,
            "status": order.status,
            "scheduled_date": order.scheduled_date,
            "scheduled_time": order.scheduled_time,
            "total_amount": order.total_amount,
        }


class TariffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tariff
        fields = ("id", "name", "description", "price", "duration_days", "is_active")


class MasterCertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterCertificate
        fields = ("id", "title", "file", "created_at")
        read_only_fields = ("id", "created_at")


class MasterDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterDocument
        fields = ("id", "title", "file", "created_at")
        read_only_fields = ("id", "created_at")


class PrivacyPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = PrivacyPolicy
        fields = ("content", "version", "updated_at")
