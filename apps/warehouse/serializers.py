from decimal import Decimal

from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.warehouse.models import MasterInventory, WarehouseCategory, WarehouseProduct
from apps.warehouse.services import adjust_master_inventory, assign_inventory_to_master


class WarehouseCategorySerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = WarehouseCategory
        fields = ("id", "name", "slug", "products_count")


class WarehouseProductSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)
    disabled = serializers.SerializerMethodField()
    category_detail = WarehouseCategorySerializer(source="category", read_only=True)
    stock_value = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = WarehouseProduct
        fields = (
            "id",
            "category",
            "category_detail",
            "name",
            "unit",
            "quantity",
            "low_threshold",
            "cost_price",
            "sale_price",
            "stock_value",
            "image",
            "is_low_stock",
            "disabled",
        )

    @extend_schema_field(serializers.BooleanField)
    def get_disabled(self, obj):
        return obj.quantity <= 0


class MasterInventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="warehouse_product.name", read_only=True)
    sale_price = serializers.DecimalField(
        source="warehouse_product.sale_price",
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = MasterInventory
        fields = (
            "id",
            "master",
            "warehouse_product",
            "product_name",
            "sale_price",
            "quantity",
            "unit",
            "low_threshold",
            "image",
            "is_low_stock",
            "assigned_at",
            "updated_at",
        )
        read_only_fields = ("master", "unit", "image", "assigned_at", "updated_at")


class AdminAssignInventorySerializer(serializers.Serializer):
    warehouse_product_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    def validate(self, attrs):
        try:
            attrs["product"] = WarehouseProduct.objects.get(id=attrs["warehouse_product_id"], is_active=True)
        except WarehouseProduct.DoesNotExist:
            raise serializers.ValidationError({"warehouse_product_id": "Mahsulot topilmadi yoki faol emas"})
        return attrs

    def save(self, **kwargs):
        return assign_inventory_to_master(
            master=self.context["master"],
            product=self.validated_data["product"],
            quantity=self.validated_data["quantity"],
        )


class AdminUpdateInventorySerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)

    def save(self, **kwargs):
        # Delegates to the locked service (moves warehouse delta + records StockMovement).
        return adjust_master_inventory(self.context["item"], self.validated_data["quantity"])


class UseInventorySerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    order_id = serializers.UUIDField()

    @transaction.atomic
    def save(self, **kwargs):
        item = self.context["item"]
        quantity = self.validated_data["quantity"]
        if item.quantity < quantity:
            raise serializers.ValidationError("Usta omborida yetarli mahsulot yo'q")
        item.quantity -= quantity
        item.save(update_fields=["quantity", "updated_at"])
        return item
