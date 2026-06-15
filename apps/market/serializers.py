from rest_framework import serializers

from apps.market.models import MarketCategory, MarketFavorite, MarketOrder, MarketProduct, MarketProductImage


class MarketCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketCategory
        fields = ("id", "name", "slug")


class MarketProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketProductImage
        fields = ("id", "image")


class MarketProductSerializer(serializers.ModelSerializer):
    images = MarketProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = MarketProduct
        fields = (
            "id",
            "category",
            "seller",
            "name",
            "description",
            "condition",
            "price",
            "quantity",
            "rating",
            "is_active",
            "is_moderated",
            "images",
            "created_at",
        )
        read_only_fields = ("id", "seller", "rating", "is_active", "is_moderated", "created_at")


class MarketOrderSerializer(serializers.ModelSerializer):
    product_detail = MarketProductSerializer(source="product", read_only=True)

    class Meta:
        model = MarketOrder
        fields = (
            "id",
            "product",
            "product_detail",
            "quantity",
            "delivery_address",
            "phone",
            "note",
            "total_amount",
            "status",
            "created_at",
        )
        read_only_fields = ("id", "total_amount", "status", "created_at")


class MarketFavoriteSerializer(serializers.ModelSerializer):
    product_detail = MarketProductSerializer(source="product", read_only=True)

    class Meta:
        model = MarketFavorite
        fields = ("id", "product", "product_detail", "created_at")
        read_only_fields = ("id", "created_at")
