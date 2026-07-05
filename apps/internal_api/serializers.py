from datetime import time
from decimal import Decimal

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from rest_framework import serializers

from apps.accounts.models import Client, Master
from apps.orders.models import Order, OrderStatus, PaymentType
from apps.orders.receipts import order_receipt_filename
from apps.profiles.models import ClientAddress, Tariff, TariffFeature
from apps.services.models import Service, ServiceCategory


MASTER_STATUS_CHOICES = ("active", "busy", "inactive", "blocked")
ORDER_STATUS_TO_DASHBOARD = {
    OrderStatus.NEW: "new",
    OrderStatus.ACCEPTED: "on_way",
    OrderStatus.IN_PROGRESS: "in_progress",
    OrderStatus.COMPLETED: "completed",
    OrderStatus.CANCELLED: "cancelled",
    OrderStatus.REJECTED: "cancelled",
}
ORDER_STATUS_FROM_DASHBOARD = {
    "new": OrderStatus.NEW,
    "on_way": OrderStatus.ACCEPTED,
    "in_progress": OrderStatus.IN_PROGRESS,
    "completed": OrderStatus.COMPLETED,
    "cancelled": OrderStatus.CANCELLED,
    "delayed": OrderStatus.ACCEPTED,
    "accepted": OrderStatus.ACCEPTED,
    "rejected": OrderStatus.REJECTED,
}


def split_full_name(value):
    value = (value or "").strip()
    if not value:
        return "", ""
    first_name, _, last_name = value.partition(" ")
    return first_name, last_name


def full_name(obj):
    if hasattr(obj, "full_name"):
        return obj.full_name
    return f"{obj.first_name} {obj.last_name}".strip() or obj.phone


def file_url(request, file_field):
    if not file_field:
        return None
    url = file_field.url
    return request.build_absolute_uri(url) if request else url


def master_status(master):
    if master.is_blocked or not master.is_active:
        return "blocked"
    if not master.is_available:
        return "busy"
    if master.is_online:
        return "active"
    return "inactive"


def apply_master_status(master, status):
    if status == "blocked":
        master.block(reason=getattr(master, "block_reason", "") or "")
    elif status == "busy":
        master.unblock()
        master.is_available = False
    elif status == "active":
        master.unblock()
        master.is_available = True
        master.is_online = True
    elif status == "inactive":
        master.unblock()
        master.is_available = True
        master.is_online = False


def dashboard_order_status(order):
    return ORDER_STATUS_TO_DASHBOARD.get(order.status, order.status)


def dashboard_payment_status(order):
    if order.status == OrderStatus.COMPLETED and order.total_amount > 0:
        return "paid"
    return "unpaid"


def parse_scheduled_at(value):
    if not value:
        return None
    if hasattr(value, "date") and hasattr(value, "time"):
        return value
    parsed = parse_datetime(str(value))
    if parsed is None:
        parsed_date = parse_date(str(value))
        if parsed_date:
            parsed = timezone.datetime.combine(parsed_date, time(hour=9))
    if parsed is None:
        raise serializers.ValidationError("scheduled_at formati noto'g'ri")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


class InternalClientSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    last_order_date = serializers.SerializerMethodField()
    current_tariff_name = serializers.CharField(source="current_tariff.name", read_only=True, allow_null=True)

    class Meta:
        model = Client
        fields = (
            "id",
            "full_name",
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "address",
            "total_spent",
            "total_orders",
            "last_order_date",
            "current_tariff",
            "current_tariff_name",
            "tariff_expires_at",
            "notifications_enabled",
            "push_enabled",
            "is_active",
            "created_at",
            "updated_at",
        )

    def get_full_name(self, obj):
        return full_name(obj)

    def get_address(self, obj):
        address = getattr(obj, "default_address", None) or obj.addresses.order_by("-is_default", "label").first()
        return address.address_text if address else ""

    def get_last_order_date(self, obj):
        order = obj.orders.order_by("-created_at").first()
        return order.created_at.date() if order else None


class InternalClientWriteSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True, write_only=True)
    lat = serializers.DecimalField(max_digits=10, decimal_places=8, required=False, write_only=True)
    lng = serializers.DecimalField(max_digits=11, decimal_places=8, required=False, write_only=True)

    class Meta:
        model = Client
        fields = (
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "avatar",
            "address",
            "lat",
            "lng",
            "language",
            "notifications_enabled",
            "push_enabled",
            "current_tariff",
            "tariff_expires_at",
            "is_active",
        )

    def validate(self, attrs):
        name = attrs.pop("full_name", "").strip()
        if name and not attrs.get("first_name"):
            attrs["first_name"], attrs["last_name"] = split_full_name(name)
        return attrs

    def _save_address(self, client, address_text, lat=None, lng=None):
        if not address_text:
            return
        address = client.addresses.filter(is_default=True).first() or client.addresses.first()
        data = {"label": "Asosiy", "address_text": address_text, "is_default": True}
        if lat is not None and lng is not None:
            data.update({"lat": lat, "lng": lng})
        elif address is None:
            return
        if address:
            for field, value in data.items():
                setattr(address, field, value)
            address.save()
        else:
            ClientAddress.objects.create(client=client, **data)

    def create(self, validated_data):
        address = validated_data.pop("address", "")
        lat = validated_data.pop("lat", None)
        lng = validated_data.pop("lng", None)
        client = super().create(validated_data)
        self._save_address(client, address, lat, lng)
        return client

    def update(self, instance, validated_data):
        address = validated_data.pop("address", "")
        lat = validated_data.pop("lat", None)
        lng = validated_data.pop("lng", None)
        client = super().update(instance, validated_data)
        self._save_address(client, address, lat, lng)
        return client


class InternalServiceSummarySerializer(serializers.ModelSerializer):
    base_price = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = Service
        fields = ("id", "name", "base_price")


class InternalMasterSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    worker_type = serializers.SerializerMethodField()
    degree = serializers.SerializerMethodField()
    role = serializers.CharField(source="specialization", read_only=True)
    skills = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    balance = serializers.SerializerMethodField()
    total_orders = serializers.SerializerMethodField()
    total_income = serializers.SerializerMethodField()
    latitude = serializers.DecimalField(source="lat", max_digits=10, decimal_places=8, read_only=True)
    longitude = serializers.DecimalField(source="lng", max_digits=11, decimal_places=8, read_only=True)
    is_verified = serializers.SerializerMethodField()
    telegram_id = serializers.SerializerMethodField()

    class Meta:
        model = Master
        fields = (
            "id",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "address",
            "worker_type",
            "degree",
            "role",
            "specialization",
            "skills",
            "avatar",
            "status",
            "rating",
            "balance",
            "total_orders",
            "total_income",
            "latitude",
            "longitude",
            "last_location_at",
            "is_verified",
            "is_online",
            "is_available",
            "is_active",
            "telegram_id",
            "created_at",
            "updated_at",
        )

    def get_full_name(self, obj):
        return full_name(obj)

    def get_address(self, obj):
        return ""

    def get_worker_type(self, obj):
        return "master"

    def get_degree(self, obj):
        return "master"

    def get_skills(self, obj):
        return []

    def get_status(self, obj):
        return master_status(obj)

    def get_balance(self, obj):
        wallet = getattr(obj, "wallet", None)
        if not wallet:
            return Decimal("0")
        return wallet.balance_online + wallet.balance_cash

    def get_total_orders(self, obj):
        return getattr(obj, "orders_count", None) or obj.orders.count()

    def get_total_income(self, obj):
        return getattr(obj, "completed_income", None) or Decimal("0")

    def get_is_verified(self, obj):
        return True

    def get_telegram_id(self, obj):
        return ""


class InternalMasterWriteSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(required=False, allow_blank=True)
    role = serializers.CharField(required=False, allow_blank=True, write_only=True)
    status = serializers.ChoiceField(choices=MASTER_STATUS_CHOICES, required=False, write_only=True)
    password = serializers.CharField(required=False, allow_blank=False, write_only=True)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=8, required=False, write_only=True)
    longitude = serializers.DecimalField(max_digits=11, decimal_places=8, required=False, write_only=True)

    class Meta:
        model = Master
        fields = (
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "password",
            "specialization",
            "role",
            "avatar",
            "rating",
            "status",
            "latitude",
            "longitude",
            "is_online",
            "is_available",
            "is_active",
            "language",
            "notifications_enabled",
            "push_enabled",
        )

    def validate(self, attrs):
        name = attrs.pop("full_name", "").strip()
        if name and not attrs.get("first_name"):
            attrs["first_name"], attrs["last_name"] = split_full_name(name)
        role = attrs.pop("role", "").strip()
        if role and not attrs.get("specialization"):
            attrs["specialization"] = role
        if "latitude" in attrs:
            attrs["lat"] = attrs.pop("latitude")
        if "longitude" in attrs:
            attrs["lng"] = attrs.pop("longitude")
        return attrs

    def create(self, validated_data):
        status = validated_data.pop("status", None)
        password = validated_data.pop("password", None)
        master = Master(**validated_data)
        if password:
            master.set_password(password)
        if status:
            apply_master_status(master, status)
        master.save()
        return master

    def update(self, instance, validated_data):
        status = validated_data.pop("status", None)
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.set_password(password)
        if status:
            apply_master_status(instance, status)
        instance.save()
        return instance


class InternalServiceCategorySerializer(serializers.ModelSerializer):
    image = serializers.ImageField(source="icon", read_only=True)
    base_tariff = serializers.SerializerMethodField()
    services_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ServiceCategory
        fields = (
            "id",
            "name",
            "slug",
            "image",
            "icon",
            "is_active",
            "base_tariff",
            "sort_order",
            "services_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")

    def get_base_tariff(self, obj):
        price = obj.services.filter(is_active=True).order_by("base_price").values_list("base_price", flat=True).first()
        return price or Decimal("0")


class InternalServiceCategoryWriteSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True, write_only=True)
    base_tariff = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, write_only=True)

    class Meta:
        model = ServiceCategory
        fields = ("name", "slug", "image", "is_active", "sort_order", "base_tariff")
        extra_kwargs = {"slug": {"required": False}}

    def validate(self, attrs):
        attrs.pop("base_tariff", None)
        if "image" in attrs:
            attrs["icon"] = attrs.pop("image")
        if not attrs.get("slug") and attrs.get("name"):
            attrs["slug"] = str(attrs["name"]).lower().replace(" ", "-")
        return attrs


class InternalServiceSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = (
            "id",
            "category",
            "category_name",
            "name",
            "description",
            "image",
            "base_price",
            "is_active",
            "created_at",
            "updated_at",
        )

    def get_image(self, obj):
        return None


class InternalServiceWriteSerializer(serializers.ModelSerializer):
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ServiceCategory.objects.all(), source="category", required=False, write_only=True
    )

    class Meta:
        model = Service
        fields = ("category", "category_id", "name", "description", "base_price", "is_active")
        extra_kwargs = {"category": {"required": False}}


class InternalTariffSerializer(serializers.ModelSerializer):
    period = serializers.SerializerMethodField()
    features = serializers.SerializerMethodField()
    max_orders = serializers.SerializerMethodField()
    max_masters = serializers.SerializerMethodField()
    has_analytics = serializers.SerializerMethodField()
    has_priority_support = serializers.SerializerMethodField()
    discount_pct = serializers.SerializerMethodField()

    class Meta:
        model = Tariff
        fields = (
            "id",
            "name",
            "price",
            "period",
            "features",
            "max_orders",
            "max_masters",
            "has_analytics",
            "has_priority_support",
            "discount_pct",
            "is_popular",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        )

    def get_period(self, obj):
        return "yearly" if obj.duration_days >= 365 else "monthly"

    def get_features(self, obj):
        return list(obj.features.order_by("sort_order", "id").values_list("title", flat=True))

    def get_max_orders(self, obj):
        return None

    def get_max_masters(self, obj):
        return None

    def get_has_analytics(self, obj):
        return False

    def get_has_priority_support(self, obj):
        return False

    def get_discount_pct(self, obj):
        return 0


class InternalTariffWriteSerializer(serializers.ModelSerializer):
    period = serializers.ChoiceField(choices=("monthly", "yearly"), required=False, write_only=True)
    features = serializers.ListField(child=serializers.CharField(), required=False, write_only=True)

    class Meta:
        model = Tariff
        fields = ("name", "price", "period", "features", "duration_days", "is_popular", "is_active", "sort_order")
        extra_kwargs = {"duration_days": {"required": False}}

    def validate(self, attrs):
        period = attrs.pop("period", None)
        if period and "duration_days" not in attrs:
            attrs["duration_days"] = 365 if period == "yearly" else 30
        return attrs

    def _save_features(self, tariff, features):
        if features is None:
            return
        tariff.features.all().delete()
        TariffFeature.objects.bulk_create(
            [TariffFeature(tariff=tariff, title=title, sort_order=index) for index, title in enumerate(features)]
        )

    def create(self, validated_data):
        features = validated_data.pop("features", None)
        tariff = super().create(validated_data)
        self._save_features(tariff, features)
        return tariff

    def update(self, instance, validated_data):
        features = validated_data.pop("features", None)
        tariff = super().update(instance, validated_data)
        self._save_features(tariff, features)
        return tariff


class InternalOrderSerializer(serializers.ModelSerializer):
    code = serializers.SerializerMethodField()
    client = serializers.UUIDField(source="client_id", read_only=True)
    client_name = serializers.SerializerMethodField()
    client_phone = serializers.CharField(source="client.phone", read_only=True)
    client_avatar = serializers.SerializerMethodField()
    service = serializers.UUIDField(source="service_id", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    service_image = serializers.SerializerMethodField()
    master = serializers.UUIDField(source="master_id", read_only=True, allow_null=True)
    master_name = serializers.SerializerMethodField()
    master_phone = serializers.CharField(source="master.phone", read_only=True, allow_null=True)
    master_avatar = serializers.SerializerMethodField()
    assistants = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_status_label = serializers.SerializerMethodField()
    price = serializers.DecimalField(source="total_amount", max_digits=12, decimal_places=2, read_only=True)
    scheduled_at = serializers.SerializerMethodField()
    address = serializers.CharField(source="address_text", read_only=True)
    time = serializers.SerializerMethodField()
    before_photo = serializers.SerializerMethodField()
    completion_photo = serializers.SerializerMethodField()
    receipt_status = serializers.SerializerMethodField()
    receipt_download_url = serializers.SerializerMethodField()
    receipt_filename = serializers.SerializerMethodField()
    can_download_receipt = serializers.SerializerMethodField()
    cancelled_reason = serializers.CharField(source="cancel_reason", read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "code",
            "client",
            "client_name",
            "client_phone",
            "client_avatar",
            "service",
            "service_name",
            "service_image",
            "master",
            "master_name",
            "master_phone",
            "master_avatar",
            "assistants",
            "status",
            "status_label",
            "payment_type",
            "payment_status",
            "payment_status_label",
            "price",
            "service_fee",
            "inventory_total",
            "bonus_used",
            "total_amount",
            "scheduled_at",
            "scheduled_date",
            "scheduled_time",
            "address",
            "address_text",
            "lat",
            "lng",
            "note",
            "time",
            "before_photo",
            "completion_photo",
            "receipt_status",
            "receipt_approved_at",
            "receipt_download_url",
            "receipt_filename",
            "can_download_receipt",
            "created_at",
            "updated_at",
            "cancelled_reason",
            "cancel_reason",
            "rejected_reason",
        )

    def get_code(self, obj):
        return f"HX{str(obj.id).split('-')[0].upper()}"

    def get_client_name(self, obj):
        return full_name(obj.client)

    def get_client_avatar(self, obj):
        return file_url(self.context.get("request"), obj.client.avatar)

    def get_service_image(self, obj):
        return None

    def get_master_name(self, obj):
        return full_name(obj.master) if obj.master else None

    def get_master_avatar(self, obj):
        return file_url(self.context.get("request"), obj.master.avatar) if obj.master else None

    def get_assistants(self, obj):
        return []

    def get_status(self, obj):
        return dashboard_order_status(obj)

    def get_status_label(self, obj):
        return dict(OrderStatus.choices).get(obj.status, obj.status)

    def get_payment_status(self, obj):
        return dashboard_payment_status(obj)

    def get_payment_status_label(self, obj):
        return "To'langan" if self.get_payment_status(obj) == "paid" else "To'lanmagan"

    def get_scheduled_at(self, obj):
        scheduled = timezone.datetime.combine(obj.scheduled_date, obj.scheduled_time)
        scheduled = timezone.make_aware(scheduled, timezone.get_current_timezone())
        return scheduled

    def get_time(self, obj):
        return timezone.localtime(obj.created_at).strftime("%H:%M") if obj.created_at else None

    def get_before_photo(self, obj):
        return file_url(self.context.get("request"), obj.before_photo)

    def get_completion_photo(self, obj):
        return file_url(self.context.get("request"), obj.completion_photo)

    def get_receipt_status(self, obj):
        if obj.receipt_approved_at:
            return "approved"
        if obj.status == OrderStatus.COMPLETED:
            return "pending_master_confirmation"
        return "not_ready"

    def get_receipt_download_url(self, obj):
        if not self.get_can_download_receipt(obj):
            return None
        return f"/api/v1/orders/{obj.id}/receipt/download/"

    def get_receipt_filename(self, obj):
        return order_receipt_filename(obj)

    def get_can_download_receipt(self, obj):
        return obj.status == OrderStatus.COMPLETED and bool(obj.receipt_approved_at)


class InternalOrderWriteSerializer(serializers.Serializer):
    client_id = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all(), source="client", required=False)
    master_id = serializers.PrimaryKeyRelatedField(
        queryset=Master.objects.filter(is_active=True), source="master", required=False, allow_null=True
    )
    service_id = serializers.PrimaryKeyRelatedField(queryset=Service.objects.filter(is_active=True), source="service", required=False)
    status = serializers.ChoiceField(choices=tuple(ORDER_STATUS_FROM_DASHBOARD.keys()), required=False)
    payment_type = serializers.ChoiceField(choices=PaymentType.choices, required=False)
    price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    scheduled_at = serializers.CharField(required=False, allow_blank=True)
    scheduled_date = serializers.CharField(required=False, allow_blank=True)
    scheduled_time = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    address_text = serializers.CharField(required=False, allow_blank=True)
    lat = serializers.DecimalField(max_digits=10, decimal_places=8, required=False)
    lng = serializers.DecimalField(max_digits=11, decimal_places=8, required=False)
    note = serializers.CharField(required=False, allow_blank=True)
    cancelled_reason = serializers.CharField(required=False, allow_blank=True)
    cancel_reason = serializers.CharField(required=False, allow_blank=True)
    rejected_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        scheduled_at = parse_scheduled_at(attrs.pop("scheduled_at", None))
        if scheduled_at:
            attrs["scheduled_date"] = scheduled_at.date()
            attrs["scheduled_time"] = scheduled_at.time()
        elif isinstance(attrs.get("scheduled_date"), str):
            parsed_date = parse_date(attrs["scheduled_date"])
            if not parsed_date:
                raise serializers.ValidationError({"scheduled_date": "scheduled_date formati noto'g'ri"})
            attrs["scheduled_date"] = parsed_date
        elif "scheduled_date" not in attrs:
            attrs["scheduled_date"] = timezone.localdate()

        if isinstance(attrs.get("scheduled_time"), str):
            parsed_time = parse_time(attrs["scheduled_time"])
            if not parsed_time:
                raise serializers.ValidationError({"scheduled_time": "scheduled_time formati noto'g'ri"})
            attrs["scheduled_time"] = parsed_time
        elif "scheduled_time" not in attrs:
            attrs["scheduled_time"] = timezone.localtime().time().replace(microsecond=0)

        if "address" in attrs and "address_text" not in attrs:
            attrs["address_text"] = attrs.pop("address")
        if "cancelled_reason" in attrs and "cancel_reason" not in attrs:
            attrs["cancel_reason"] = attrs.pop("cancelled_reason")
        if "status" in attrs:
            attrs["status"] = ORDER_STATUS_FROM_DASHBOARD[attrs["status"]]
        return attrs

    def create(self, validated_data):
        price = validated_data.pop("price", None)
        service = validated_data.get("service")
        validated_data.setdefault("address_text", "")
        validated_data.setdefault("lat", Decimal("0"))
        validated_data.setdefault("lng", Decimal("0"))
        validated_data.setdefault("payment_type", PaymentType.CASH)
        validated_data.setdefault("status", OrderStatus.NEW)
        if price is None:
            price = service.base_price if service else Decimal("0")
        validated_data.setdefault("service_fee", price)
        validated_data.setdefault("total_amount", price)
        order = Order.objects.create(**validated_data)
        order.recalculate_total()
        order.save(update_fields=("total_amount",))
        return order

    def update(self, instance, validated_data):
        price = validated_data.pop("price", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if price is not None:
            instance.service_fee = price
            instance.total_amount = price
        instance.recalculate_total()
        instance.save()
        return instance
