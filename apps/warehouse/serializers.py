from django.db import transaction
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.warehouse.models import MasterInventory, StockMovement, WarehouseProduct


class WarehouseProductSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)
    disabled = serializers.SerializerMethodField()

    class Meta:
        model = WarehouseProduct
        fields = ("id", "name", "unit", "quantity", "low_threshold", "image", "is_low_stock", "disabled")

    @extend_schema_field(serializers.BooleanField)
    def get_disabled(self, obj):
        return obj.quantity <= 0


class MasterInventorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="warehouse_product.name", read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = MasterInventory
        fields = (
            "id",
            "master",
            "warehouse_product",
            "product_name",
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
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)

    def validate(self, attrs):
        product = WarehouseProduct.objects.get(id=attrs["warehouse_product_id"], is_active=True)
        if product.quantity < attrs["quantity"]:
            raise serializers.ValidationError("Omborda yetarli mahsulot yo'q")
        attrs["product"] = product
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        master = self.context["master"]
        product = self.validated_data["product"]
        quantity = self.validated_data["quantity"]
        item, _ = MasterInventory.objects.select_for_update().get_or_create(
            master=master,
            warehouse_product=product,
            defaults={
                "quantity": 0,
                "unit": product.unit,
                "low_threshold": product.low_threshold,
                "image": product.image,
            },
        )
        item.quantity += quantity
        item.save()
        product.quantity -= quantity
        product.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            product=product,
            movement_type=StockMovement.OUT,
            quantity=quantity,
            master=master,
            note=f"Ustaga biriktirildi: {master}",
        )
        return item


class AdminUpdateInventorySerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)

    @transaction.atomic
    def save(self, **kwargs):
        item = self.context["item"]
        product = item.warehouse_product
        new_quantity = self.validated_data["quantity"]
        delta = new_quantity - item.quantity
        if delta > 0 and product.quantity < delta:
            raise serializers.ValidationError("Omborda yetarli mahsulot yo'q")
        product.quantity -= delta
        product.save(update_fields=["quantity", "updated_at"])
        item.quantity = new_quantity
        item.save(update_fields=["quantity", "updated_at"])
        StockMovement.objects.create(
            product=product,
            movement_type=StockMovement.OUT if delta > 0 else StockMovement.IN,
            quantity=abs(delta),
            master=item.master,
            note=f"Usta biriktirish miqdori o'zgardi: {item.master}",
        )
        return item


class UseInventorySerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0)
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
