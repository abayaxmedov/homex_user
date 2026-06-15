from rest_framework import serializers

from apps.services.models import Service, ServiceCategory, ServicePrice


class ServicePriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePrice
        fields = ("id", "title", "price", "unit", "is_active")


class ServiceSerializer(serializers.ModelSerializer):
    prices = ServicePriceSerializer(many=True, read_only=True)

    class Meta:
        model = Service
        fields = ("id", "category", "name", "description", "base_price", "is_active", "prices")


class ServiceCategorySerializer(serializers.ModelSerializer):
    services = ServiceSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceCategory
        fields = ("id", "name", "slug", "icon", "is_active", "sort_order", "services")
