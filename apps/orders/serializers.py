from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers


@extend_schema_field(OpenApiTypes.BINARY)
class UploadImageField(serializers.ImageField):
    """ImageField that Swagger renders as a file-upload (binary), not a URL string."""

from apps.accounts.models import Master
from apps.accounts.serializers import MasterSummarySerializer
from apps.integrations.adapters import PaymentClient
from apps.orders.models import Order, OrderInventoryUsage, OrderStatus, OrderTracking, PaymentType, Review, ReviewPhoto
from apps.orders.receipts import order_receipt_filename
from apps.orders.tracking import ensure_tracking, tracking_state
from apps.profiles.models import ClientAddress, ClientDevice
from apps.services.serializers import ServiceSerializer
from apps.wallet.models import MasterWallet, WalletTransaction
from apps.warehouse.models import MasterInventory


class OrderInventoryUsageSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="inventory.warehouse_product.name", read_only=True)

    class Meta:
        model = OrderInventoryUsage
        fields = ("id", "inventory", "product_name", "quantity", "unit_price", "total_price")
        read_only_fields = ("id", "product_name", "total_price")


class OrderTrackingSerializer(serializers.ModelSerializer):
    tracking_status = serializers.SerializerMethodField()
    tracking_status_label = serializers.SerializerMethodField()
    tracking_step = serializers.SerializerMethodField()
    tracking_total_steps = serializers.SerializerMethodField()
    tracking_steps = serializers.SerializerMethodField()

    class Meta:
        model = OrderTracking
        fields = (
            "tracking_status",
            "tracking_status_label",
            "tracking_step",
            "tracking_total_steps",
            "tracking_steps",
            "master_lat",
            "master_lng",
            "distance_km",
            "eta_minutes",
            "updated_at",
        )
        read_only_fields = fields

    def _state(self, obj):
        return tracking_state(obj.order)

    @extend_schema_field(serializers.CharField)
    def get_tracking_status(self, obj):
        return self._state(obj)["key"]

    @extend_schema_field(serializers.CharField)
    def get_tracking_status_label(self, obj):
        return self._state(obj)["label"]

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_tracking_step(self, obj):
        return self._state(obj)["step"]

    @extend_schema_field(serializers.IntegerField)
    def get_tracking_total_steps(self, obj):
        return self._state(obj)["total_steps"]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_tracking_steps(self, obj):
        return self._state(obj)["steps"]


class OrderSerializer(serializers.ModelSerializer):
    service_detail = ServiceSerializer(source="service", read_only=True)
    master_detail = MasterSummarySerializer(source="master", read_only=True)
    inventory_usages = OrderInventoryUsageSerializer(many=True, read_only=True)
    tracking = OrderTrackingSerializer(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    tracking_status = serializers.SerializerMethodField()
    tracking_status_label = serializers.SerializerMethodField()
    tracking_step = serializers.SerializerMethodField()
    tracking_total_steps = serializers.SerializerMethodField()
    tracking_steps = serializers.SerializerMethodField()
    master_phone_number = serializers.CharField(source="master.phone", read_only=True)
    payment_type_label = serializers.CharField(source="get_payment_type_display", read_only=True)
    can_cancel = serializers.SerializerMethodField(help_text="Frontend cancel button ko'rsatishi mumkinmi.")
    can_rate = serializers.SerializerMethodField(help_text="Frontend rating modal/button ko'rsatishi mumkinmi.")
    can_download_receipt = serializers.SerializerMethodField(help_text="Client checkni yuklab olishi mumkinmi.")
    receipt_status = serializers.SerializerMethodField()
    receipt_download_url = serializers.SerializerMethodField()
    receipt_filename = serializers.SerializerMethodField()
    device_detail = serializers.SerializerMethodField(help_text="Orderga bog'langan qurilma ma'lumoti.")
    # Inline device capture: yangi qurilmani order bilan birga saqlash uchun (write-only).
    device_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    device_model = serializers.CharField(write_only=True, required=False, allow_blank=True)
    device_image = serializers.ImageField(write_only=True, required=False, allow_null=True)
    device_location_label = serializers.CharField(write_only=True, required=False, allow_blank=True)

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
            "device",
            "device_detail",
            "device_name",
            "device_model",
            "device_image",
            "device_location_label",
            "address_text",
            "lat",
            "lng",
            "scheduled_date",
            "scheduled_time",
            "note",
            "status",
            "status_label",
            "tracking_status",
            "tracking_status_label",
            "tracking_step",
            "tracking_total_steps",
            "tracking_steps",
            "payment_type",
            "payment_type_label",
            "master_phone_number",
            "service_fee",
            "inventory_total",
            "bonus_used",
            "total_amount",
            "before_photo",
            "completion_photo",
            "receipt_status",
            "receipt_approved_at",
            "receipt_download_url",
            "receipt_filename",
            "can_download_receipt",
            "cancel_reason",
            "rejected_reason",
            "inventory_usages",
            "tracking",
            "can_cancel",
            "can_rate",
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
            "before_photo",
            "completion_photo",
            "receipt_approved_at",
            "created_at",
        )
        extra_kwargs = {
            "status": {
                "help_text": "`new`, `accepted`, `on_way`, `arrived`, `completed`, `cancelled`, `rejected`."
            },
            "payment_type": {"help_text": "`cash`, `online`, `card`, `plastic`."},
            "bonus_used": {"help_text": "Client ishlatgan bonus summa. Totaldan ayriladi."},
            "total_amount": {"help_text": "service_fee + inventory_total - bonus_used."},
        }

    @extend_schema_field(serializers.BooleanField)
    def get_can_cancel(self, obj):
        return obj.status in {OrderStatus.NEW, OrderStatus.ACCEPTED, OrderStatus.ON_WAY}

    @extend_schema_field(serializers.BooleanField)
    def get_can_rate(self, obj):
        return obj.status == OrderStatus.COMPLETED and not hasattr(obj, "review")

    @extend_schema_field(serializers.BooleanField)
    def get_can_download_receipt(self, obj):
        return obj.status == OrderStatus.COMPLETED and bool(obj.receipt_approved_at)

    @extend_schema_field(serializers.CharField)
    def get_receipt_status(self, obj):
        if obj.receipt_approved_at:
            return "approved"
        if obj.status == OrderStatus.COMPLETED:
            return "pending_master_confirmation"
        return "not_ready"

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_receipt_download_url(self, obj):
        if not self.get_can_download_receipt(obj):
            return None
        url = reverse("client-order-receipt-download", args=[obj.id])
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    @extend_schema_field(serializers.CharField)
    def get_receipt_filename(self, obj):
        return order_receipt_filename(obj)

    def _tracking_state(self, obj):
        return tracking_state(obj)

    @extend_schema_field(serializers.CharField)
    def get_tracking_status(self, obj):
        return self._tracking_state(obj)["key"]

    @extend_schema_field(serializers.CharField)
    def get_tracking_status_label(self, obj):
        return self._tracking_state(obj)["label"]

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_tracking_step(self, obj):
        return self._tracking_state(obj)["step"]

    @extend_schema_field(serializers.IntegerField)
    def get_tracking_total_steps(self, obj):
        return self._tracking_state(obj)["total_steps"]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_tracking_steps(self, obj):
        return self._tracking_state(obj)["steps"]

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_device_detail(self, obj):
        if not obj.device_id:
            return None
        from apps.profiles.serializers import ClientDeviceSerializer

        return ClientDeviceSerializer(obj.device, context=self.context).data

    def _resolve_device(self, client, order, device, device_fields):
        """Return the ClientDevice to attach to the order.

        Priority: an existing ``device`` (must belong to the client), otherwise
        a brand-new device built from the inline ``device_*`` fields and saved
        at the order's location so it is available for future orders.
        """
        if device is not None:
            if device.client_id != client.id:
                raise serializers.ValidationError({"device": "Bu qurilma sizga tegishli emas."})
            return device

        name = (device_fields.get("device_name") or "").strip()
        if not name:
            return None

        address = order.address
        if address is None:
            if order.lat is None or order.lng is None or not order.address_text:
                raise serializers.ValidationError(
                    {"device_name": "Qurilmani saqlash uchun manzil kerak (address yoki address_text + lat + lng)."}
                )
            address, _ = ClientAddress.objects.get_or_create(
                client=client,
                lat=order.lat,
                lng=order.lng,
                defaults={
                    "label": (device_fields.get("device_location_label") or "").strip() or "Manzil",
                    "address_text": order.address_text,
                },
            )

        return ClientDevice.objects.create(
            client=client,
            name=name,
            model=(device_fields.get("device_model") or "").strip(),
            image=device_fields.get("device_image"),
            address=address,
        )

    def create(self, validated_data):
        device = validated_data.pop("device", None)
        device_fields = {
            key: validated_data.pop(key, None)
            for key in ("device_name", "device_model", "device_image", "device_location_label")
        }
        service = validated_data["service"]
        validated_data["service_fee"] = service.base_price
        order = Order(**validated_data)
        order.recalculate_total()
        order.device = self._resolve_device(validated_data["client"], order, device, device_fields)
        order.save()
        ensure_tracking(order)
        return order


class OrderCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class OrderRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class OrderStartSerializer(serializers.Serializer):
    before_photo = UploadImageField(required=False)

    @transaction.atomic
    def save(self, **kwargs):
        order = self.context["order"]
        before_photo = self.validated_data.get("before_photo")

        if order.status == OrderStatus.ARRIVED:
            if before_photo:
                order.before_photo = before_photo
                order.save(update_fields=["before_photo", "updated_at"])
            return order

        if order.status != OrderStatus.ON_WAY:
            raise serializers.ValidationError({"status": "Order faqat 'on_way' holatidan 'arrived' holatiga o'tadi"})

        update_fields = ["status", "updated_at"]
        order.status = OrderStatus.ARRIVED
        if before_photo:
            order.before_photo = before_photo
            update_fields.append("before_photo")
        order.save(update_fields=update_fields)
        return order


class OrderCompleteSerializer(serializers.Serializer):
    service_fee = serializers.DecimalField(max_digits=12, decimal_places=2)
    completion_photo = UploadImageField(required=False)
    used_items = serializers.ListField(child=serializers.DictField(), required=False)

    @transaction.atomic
    def save(self, **kwargs):
        order = self.context["order"]
        order.service_fee = self.validated_data["service_fee"]
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
        if not order.receipt_approved_at:
            order.receipt_approved_at = timezone.now()
            order.receipt_approved_by = order.master
        order.recalculate_total()
        order.save()
        wallet, _ = MasterWallet.objects.get_or_create(master=order.master)
        if order.payment_type == PaymentType.ONLINE:
            payment_method = WalletTransaction.ONLINE
            MasterWallet.objects.filter(pk=wallet.pk).update(
                balance_online=F("balance_online") + order.total_amount,
                total_earned=F("total_earned") + order.total_amount,
                updated_at=timezone.now(),
            )
        else:
            payment_method = WalletTransaction.CASH
            MasterWallet.objects.filter(pk=wallet.pk).update(
                balance_cash=F("balance_cash") + order.total_amount,
                total_earned=F("total_earned") + order.total_amount,
                updated_at=timezone.now(),
            )
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
    payment_method = serializers.ChoiceField(
        choices=(("card", "Karta"), ("online", "Online"), ("plastic", "Plastik")),
        help_text="Payment start method: `card`, `online`, `plastic`.",
    )
    bonus_used = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        default=0,
        help_text="Client ishlatmoqchi bo'lgan bonus summa.",
    )
    receipt = serializers.FileField(required=False)

    def create(self, validated_data):
        order = self.context["order"]
        order.bonus_used = validated_data.get("bonus_used", 0)
        order.recalculate_total()
        order.save(update_fields=["bonus_used", "total_amount", "updated_at"])
        return PaymentClient().create_payment(order, validated_data["payment_method"]).payload


class NearbyMasterSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    distance_km = serializers.SerializerMethodField()
    eta_minutes = serializers.SerializerMethodField()

    class Meta:
        model = Master
        fields = (
            "id",
            "full_name",
            "specialization",
            "avatar",
            "rating",
            "is_online",
            "is_available",
            "lat",
            "lng",
            "last_location_at",
            "distance_km",
            "eta_minutes",
        )

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_distance_km(self, obj):
        return getattr(obj, "distance_km", None)

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_eta_minutes(self, obj):
        return getattr(obj, "eta_minutes", None)


class MasterLocationSerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=10, decimal_places=8)
    lng = serializers.DecimalField(max_digits=11, decimal_places=8)
    is_online = serializers.BooleanField(required=False, default=True)
    is_available = serializers.BooleanField(required=False, default=True)
    order_id = serializers.UUIDField(required=False)
    distance_km = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    eta_minutes = serializers.IntegerField(required=False, min_value=1)


class MapConfigSerializer(serializers.Serializer):
    provider = serializers.CharField()
    google_maps_api_key = serializers.CharField(allow_blank=True)
    default_center = serializers.DictField()
    default_zoom = serializers.IntegerField()
    tracking_ws_template = serializers.CharField()
    auth_header = serializers.CharField()
