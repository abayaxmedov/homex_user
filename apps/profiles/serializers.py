from rest_framework import serializers

from apps.profiles.models import (
    ClientAddress,
    ClientDevice,
    MasterCertificate,
    MasterDocument,
    PrivacyPolicy,
    Tariff,
)


class ClientAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientAddress
        fields = ("id", "label", "address_text", "lat", "lng", "is_default", "created_at")
        read_only_fields = ("id", "created_at")


class ClientDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientDevice
        fields = ("id", "name", "category", "model", "image", "address", "status", "created_at")
        read_only_fields = ("id", "created_at")


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
