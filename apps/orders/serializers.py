from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Master
from apps.accounts.serializers import MasterSummarySerializer
from apps.integrations.adapters import PaymentClient
from apps.orders.models import Order, OrderInventoryUsage, OrderStatus, PaymentType, Review, ReviewPhoto
from apps.services.serializers import ServiceSerializer
from apps.wallet.models import MasterWallet, WalletTransaction
from apps.warehouse.models import MasterInventory


class OrderInventoryUsageSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="inventory.warehouse_product.name", read_only=True)

    class Meta:
        model = OrderInventoryUsage
        fields = ("id", "inventory", "product_name", "quantity", "unit_price", "total_price")
        read_only_fields = ("id", "product_name", "total_price")


class OrderSerializer(serializers.ModelSerializer):
    service_detail = ServiceSerializer(source="service", read_only=True)
    master_detail = MasterSummarySerializer(source="master", read_only=True)
    inventory_usages = OrderInventoryUsageSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "client",
            "master",
            "master_detail",
            "service",
            "service_detail",
            "address",
            "address_text",
            "lat",
            "lng",
            "scheduled_date",
            "scheduled_time",
            "note",
            "status",
            "payment_type",
            "service_fee",
            "inventory_total",
            "bonus_used",
            "total_amount",
            "completion_photo",
            "cancel_reason",
            "rejected_reason",
            "inventory_usages",
            "created_at",
        )
        read_only_fields = (
            "id",
            "client",
            "master",
            "status",
            "service_fee",
            "inventory_total",
            "total_amount",
            "created_at",
        )

    def create(self, validated_data):
        service = validated_data["service"]
        validated_data["service_fee"] = service.base_price
        order = Order(**validated_data)
        order.recalculate_total()
        order.save()
        return order


class OrderCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class OrderRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class OrderCompleteSerializer(serializers.Serializer):
    service_fee = serializers.DecimalField(max_digits=12, decimal_places=2)
    payment_type = serializers.ChoiceField(choices=PaymentType.choices)
    completion_photo = serializers.ImageField(required=False)
    used_items = serializers.ListField(child=serializers.DictField(), required=False)

    @transaction.atomic
    def save(self, **kwargs):
        order = self.context["order"]
        order.service_fee = self.validated_data["service_fee"]
        order.payment_type = self.validated_data["payment_type"]
        if self.validated_data.get("completion_photo"):
            order.completion_photo = self.validated_data["completion_photo"]
        inventory_total = 0
        for item in self.validated_data.get("used_items", []):
            inventory = MasterInventory.objects.select_for_update().get(id=item["inventory_id"], master=order.master)
            quantity = item["quantity"]
            unit_price = item.get("unit_price", 0)
            if inventory.quantity < quantity:
                raise serializers.ValidationError("Usta omborida yetarli mahsulot yo'q")
            inventory.quantity -= quantity
            inventory.save(update_fields=["quantity", "updated_at"])
            usage = OrderInventoryUsage.objects.create(
                order=order,
                inventory=inventory,
                quantity=quantity,
                unit_price=unit_price,
            )
            inventory_total += usage.total_price
        order.inventory_total = inventory_total
        order.status = OrderStatus.COMPLETED
        order.recalculate_total()
        order.save()
        wallet, _ = MasterWallet.objects.get_or_create(master=order.master)
        if order.payment_type == PaymentType.ONLINE:
            wallet.balance_online += order.total_amount
            payment_method = WalletTransaction.ONLINE
        else:
            wallet.balance_cash += order.total_amount
            payment_method = WalletTransaction.CASH
        wallet.total_earned += order.total_amount
        wallet.save()
        WalletTransaction.objects.create(
            master=order.master,
            transaction_type=WalletTransaction.IN,
            amount=order.total_amount,
            description=str(order.service),
            payment_method=payment_method,
            order=order,
        )
        return order


class ReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ("id", "order", "master", "client", "rating", "comment", "is_official", "created_at")
        read_only_fields = ("id", "order", "master", "client", "is_official", "created_at")

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating 1 dan 5 gacha bo'lishi kerak")
        return value


class PaymentStartSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=(("card", "Karta"), ("online", "Online"), ("plastic", "Plastik")))
    bonus_used = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    receipt = serializers.FileField(required=False)

    def create(self, validated_data):
        order = self.context["order"]
        order.bonus_used = validated_data.get("bonus_used", 0)
        order.recalculate_total()
        order.save(update_fields=["bonus_used", "total_amount", "updated_at"])
        return PaymentClient().create_payment(order, validated_data["payment_method"]).payload


class NearbyMasterSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Master
        fields = ("id", "full_name", "specialization", "avatar", "rating", "is_online")
