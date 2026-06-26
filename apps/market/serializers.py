from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.serializers import ClientSerializer
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
    images_upload = serializers.ListField(child=serializers.ImageField(), write_only=True, required=False)
    category_detail = MarketCategorySerializer(source="category", read_only=True)
    seller_detail = ClientSerializer(source="seller", read_only=True)
    is_favorite = serializers.SerializerMethodField()

    class Meta:
        model = MarketProduct
        fields = (
            "id",
            "category",
            "category_detail",
            "seller",
            "seller_detail",
            "name",
            "description",
            "condition",
            "price",
            "quantity",
            "rating",
            "is_active",
            "is_moderated",
            "images",
            "images_upload",
            "is_favorite",
            "created_at",
        )
        read_only_fields = ("id", "seller", "rating", "is_active", "is_moderated", "created_at")
        extra_kwargs = {
            "condition": {"help_text": "`new` - yangi mahsulot, `used` - ishlatilgan mahsulot."},
            "is_moderated": {"help_text": "Admin/moderation tasdiqlaganmi. Client listing create qilinganda false bo'ladi."},
        }

    @extend_schema_field(serializers.BooleanField)
    def get_is_favorite(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or getattr(user, "role", None) != "client":
            return False
        return MarketFavorite.objects.filter(client=user, product=obj).exists()

    def create(self, validated_data):
        images = validated_data.pop("images_upload", [])
        product = super().create(validated_data)
        MarketProductImage.objects.bulk_create(
            [MarketProductImage(product=product, image=image) for image in images]
        )
        return product


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
        extra_kwargs = {
            "status": {"help_text": "`pending`, `confirmed`, `delivered`, `cancelled`."},
            "total_amount": {"help_text": "product.price * quantity."},
        }


class MarketFavoriteSerializer(serializers.ModelSerializer):
    product_detail = MarketProductSerializer(source="product", read_only=True)

    class Meta:
        model = MarketFavorite
        fields = ("id", "product", "product_detail", "created_at")
        read_only_fields = ("id", "created_at")

class MarketCategoryListSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketCategory
        fields = ("id", "name", "slug")