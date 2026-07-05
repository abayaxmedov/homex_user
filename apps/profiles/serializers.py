from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.profiles.models import (
    ClientAddress,
    ClientDevice,
    MasterCertificate,
    MasterDocument,
    PrivacyPolicy,
    Tariff, TariffFeature,
)


class ClientAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientAddress
        fields = ("id", "label", "address_text", "lat", "lng", "is_default", "created_at")
        read_only_fields = ("id", "created_at")


class ClientDeviceSerializer(serializers.ModelSerializer):
    address_detail = ClientAddressSerializer(source="address", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    order_count = serializers.SerializerMethodField()
    last_order = serializers.SerializerMethodField()

    class Meta:
        model = ClientDevice
        # Figma "Yangi uskuna" form: name, model, image, address.
        fields = (
            "id",
            "name",
            "model",
            "image",
            "address",
            "address_detail",
            "status",
            "status_label",
            "order_count",
            "last_order",
            "created_at",
        )
        read_only_fields = ("id", "status_label", "created_at")

    @extend_schema_field(serializers.IntegerField)
    def get_order_count(self, obj):
        # Orders explicitly linked to this device (Order.device).
        return obj.orders.count()

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_last_order(self, obj):
        order = obj.orders.order_by("-created_at").first()
        if not order:
            return None
        return {
            "id": order.id,
            "status": order.status,
            "scheduled_date": order.scheduled_date,
            "scheduled_time": order.scheduled_time,
            "total_amount": order.total_amount,
        }

class TariffFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = TariffFeature
        fields = [
            "id",
            "title",
            "sort_order",
        ]

class TariffSerializer(serializers.ModelSerializer):
    features = TariffFeatureSerializer(many=True, read_only=True)

    class Meta:
        model = Tariff
        fields = ("id", "name", "price", "duration_days", "is_active", "is_popular", "features")


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
