from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import Client, Master, MasterApprovalStatus
from apps.dashboard.models import (
    DashboardBackup,
    DashboardCompanyExpense,
    DashboardIntegrationSetting,
    DashboardLiveStream,
    DashboardOrderAssistant,
    DashboardStaffProfile,
    DashboardWarehouseExpense,
)
from apps.dashboard.realtime import broadcast_dashboard_order
from apps.market.models import MarketCategory, MarketOrder, MarketProduct, MarketProductImage
from apps.market.services import place_market_order
from apps.notifications.models import Notification
from apps.orders.models import STATUS_TAB, Order, OrderMaster, OrderStatus, OrderTracking, can_admin_set_status
from apps.orders.tracking import ensure_tracking, tracking_state
from apps.notifications.services import create_notification
from apps.profiles.models import Tariff, TariffFeature
from apps.services.models import Service, ServiceCategory, ServicePrice
from apps.support.models import SupportMessage
from apps.wallet.models import MasterExpense, MasterWallet, WalletTransaction, WithdrawRequest
from apps.warehouse.models import MasterInventory, StockMovement, WarehouseCategory, WarehouseProduct
from apps.warehouse.services import assign_inventory_to_master


DASHBOARD_ROLE = "admin"

DASHBOARD_PERMISSION_LABELS = {
    "dashboard": "Dashboard",
    "orders": "Buyurtmalar",
    "clients": "Mijozlar",
    "marketplace": "Marketplace",
    "tariffs": "Tariflar",
    "live": "Jonli kuzatuv",
    "live_tracking": "Jonli kuzatuv",
    "messages": "Xabarlar",
    "support": "Xabarlar",
    "services": "Xizmat va Narxlar",
    "masters": "Ustalar",
    "warehouse": "Ombor",
    "expenses": "Xarajatlar",
    "finance": "Moliya va Hisobot",
    "staff": "Xodimlar",
}


def dashboard_permission_label(permission):
    return DASHBOARD_PERMISSION_LABELS.get(permission, str(permission).replace("_", " ").title())


def dashboard_role_label(role):
    return dict(DashboardStaffProfile.ROLES).get(role, str(role).replace("_", " ").title())


def dashboard_permissions_payload(profile, user=None):
    permissions = list(getattr(profile, "permissions", []) or [])
    is_all = bool(getattr(user, "is_superuser", False) or getattr(profile, "role", "") == DashboardStaffProfile.ADMIN)
    labels = [dashboard_permission_label(permission) for permission in permissions]
    return {
        "permissions": permissions,
        "permissions_count": None if is_all else len(permissions),
        "permissions_display": "Barcha" if is_all else f"{len(permissions)}-ta bo'lim",
        "permissions_label": "Barcha" if is_all else ", ".join(labels),
    }


def issue_dashboard_tokens(user):
    access = AccessToken()
    access.set_exp(from_time=timezone.now(), lifetime=timedelta(days=settings.ACCESS_TOKEN_DAYS))
    access["sub"] = str(user.id)
    access["role"] = DASHBOARD_ROLE
    access["username"] = user.get_username()

    refresh = RefreshToken()
    refresh.set_exp(from_time=timezone.now(), lifetime=timedelta(days=settings.REFRESH_TOKEN_DAYS))
    refresh["sub"] = str(user.id)
    refresh["role"] = DASHBOARD_ROLE

    return {
        "access_token": str(access),
        "refresh_token": str(refresh),
        "expires_in": settings.ACCESS_TOKEN_DAYS * 24 * 60 * 60,
        "user": DashboardMeSerializer(user).data,
    }


class DashboardLoginSerializer(serializers.Serializer):
    username = serializers.CharField(help_text="Django admin username/login.")
    password = serializers.CharField(write_only=True, help_text="Django admin password.")

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["username"],
            password=attrs["password"],
        )
        if not user or not user.is_active or not user.is_staff:
            raise serializers.ValidationError("Username yoki parol noto'g'ri yoki user staff emas")
        attrs["user"] = user
        return attrs

    def create(self, validated_data):
        return issue_dashboard_tokens(validated_data["user"])


class DashboardRefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(help_text="Dashboard login qaytargan refresh_token.")

    def create(self, validated_data):
        try:
            refresh = RefreshToken(validated_data["refresh_token"])
        except TokenError as exc:
            raise serializers.ValidationError({"refresh_token": str(exc)}) from exc
        if refresh.get("role") != DASHBOARD_ROLE:
            raise serializers.ValidationError("Refresh token dashboard admin uchun emas")
        user_model = get_user_model()
        try:
            user = user_model.objects.get(id=refresh.get("sub"), is_active=True, is_staff=True)
        except user_model.DoesNotExist as exc:
            raise serializers.ValidationError("Admin user topilmadi") from exc
        return issue_dashboard_tokens(user)


class DashboardLogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(help_text="Blacklist qilinadigan refresh token.")

    def save(self, **kwargs):
        try:
            RefreshToken(self.validated_data["refresh_token"]).blacklist()
        except TokenError as exc:
            raise serializers.ValidationError({"refresh_token": str(exc)}) from exc
        return {}


class DashboardMeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField(help_text="Adminning to'liq ismi yoki username.")
    role = serializers.SerializerMethodField(help_text="Dashboard JWT role qiymati: `admin`.")

    class Meta:
        model = get_user_model()
        fields = ("id", "username", "full_name", "email", "role", "is_staff", "is_superuser", "last_login")
        read_only_fields = fields

    @extend_schema_field(serializers.CharField)
    def get_full_name(self, obj):
        return obj.get_full_name() or obj.get_username()

    @extend_schema_field(serializers.CharField)
    def get_role(self, obj):
        return DASHBOARD_ROLE


class DashboardQuerySerializer(serializers.Serializer):
    date = serializers.DateField(required=False, help_text="Dashboard statistikasi uchun sana. Default: bugungi sana.")
    period = serializers.ChoiceField(
        choices=("day", "week", "month", "year"),
        default="week",
        help_text="Chart/filter period qiymati.",
    )
    orders_limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=10)


class EmptySerializer(serializers.Serializer):
    pass


class DateRangeQuerySerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=20, default=10)


class DashboardClientMiniSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = ("id", "full_name", "phone", "avatar")
        read_only_fields = fields

    @extend_schema_field(serializers.CharField)
    def get_full_name(self, obj):
        return str(obj)


class DashboardMasterMiniSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Master
        fields = ("id", "full_name", "phone", "avatar", "rating", "is_online", "is_available")
        read_only_fields = fields


class DashboardServicePriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePrice
        fields = ("id", "title", "price", "unit", "is_active")
        read_only_fields = ("id",)


class DashboardServiceCategorySerializer(serializers.ModelSerializer):
    services_count = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCategory
        fields = ("id", "name", "slug", "icon", "is_active", "sort_order", "services_count", "created_at", "updated_at")
        read_only_fields = ("id", "services_count", "created_at", "updated_at")

    @extend_schema_field(serializers.IntegerField)
    def get_services_count(self, obj):
        return getattr(obj, "services_count", obj.services.count())


class DashboardServiceMiniSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Service
        fields = ("id", "category", "category_name", "name", "base_price", "is_active")
        read_only_fields = fields


class DashboardServiceSerializer(serializers.ModelSerializer):
    category_detail = DashboardServiceCategorySerializer(source="category", read_only=True)
    prices = DashboardServicePriceSerializer(many=True, read_only=True)

    class Meta:
        model = Service
        fields = (
            "id",
            "category",
            "category_detail",
            "name",
            "description",
            "base_price",
            "is_active",
            "prices",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "category_detail", "prices", "created_at", "updated_at")


class DashboardTariffFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = TariffFeature
        fields = ("id", "title", "sort_order")
        read_only_fields = ("id",)


class DashboardTariffSerializer(serializers.ModelSerializer):
    features = DashboardTariffFeatureSerializer(many=True, read_only=True)
    clients_count = serializers.SerializerMethodField()

    class Meta:
        model = Tariff
        fields = (
            "id",
            "name",
            "price",
            "duration_days",
            "is_popular",
            "is_active",
            "sort_order",
            "features",
            "clients_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "features", "clients_count", "created_at", "updated_at")

    @extend_schema_field(serializers.IntegerField)
    def get_clients_count(self, obj):
        return getattr(obj, "clients_count", obj.clients.count())


class DashboardClientSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField(help_text="Client first_name + last_name, bo'sh bo'lsa phone.")
    current_tariff = serializers.SerializerMethodField(help_text="Client ulangan tarif nomi. ID emas.")
    current_tariff_id = serializers.PrimaryKeyRelatedField(
        source="current_tariff",
        queryset=Tariff.objects.all(),
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Dashboard update uchun tariff ID.",
    )
    addresses_count = serializers.SerializerMethodField(help_text="Clientga tegishli manzillar soni.")
    address = serializers.SerializerMethodField(help_text="Mijozning asosiy (default) manzili matni; manzil bo'lmasa null.")
    last_order_date = serializers.SerializerMethodField(help_text="Clientning oxirgi order created_at sanasi.")
    # Computed live: the stored Client.total_spent/total_orders are never maintained,
    # so read them from the orders instead of returning stale zeros. Same field names
    # and formats as before, so the response contract is unchanged.
    total_spent = serializers.SerializerMethodField(help_text="Yakunlangan buyurtmalar umumiy summasi.")
    total_orders = serializers.SerializerMethodField(help_text="Clientning umumiy buyurtmalari soni.")

    class Meta:
        model = Client
        fields = (
            "id",
            "phone",
            "first_name",
            "last_name",
            "full_name",
            "avatar",
            "language",
            "notifications_enabled",
            "push_enabled",
            "current_tariff",
            "current_tariff_id",
            "tariff_expires_at",
            "addresses_count",
            "address",
            "total_spent",
            "total_orders",
            "is_active",
            "last_order_date",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "full_name",
            "current_tariff",
            "addresses_count",
            "address",
            "total_spent",
            "total_orders",
            "last_order_date",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(serializers.CharField)
    def get_full_name(self, obj):
        return str(obj)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_current_tariff(self, obj):
        return obj.current_tariff.name if obj.current_tariff else None

    @extend_schema_field(serializers.IntegerField)
    def get_addresses_count(self, obj):
        return getattr(obj, "addresses_count", obj.addresses.count())

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_address(self, obj):
        # Prefer the client's default address; fall back to the first one. Uses the
        # prefetched ``addresses`` (ordered -is_default, label) so no extra query per row.
        addresses = list(obj.addresses.all())
        if not addresses:
            return None
        primary = next((a for a in addresses if a.is_default), addresses[0])
        return primary.address_text

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_last_order_date(self, obj):
        order = obj.orders.order_by("-created_at").first()
        return order.created_at if order else None

    @extend_schema_field(serializers.DecimalField(max_digits=14, decimal_places=2))
    def get_total_spent(self, obj):
        total = obj.orders.filter(status=OrderStatus.COMPLETED).aggregate(total=Sum("total_amount"))["total"]
        return f"{Decimal(total or 0):.2f}"

    @extend_schema_field(serializers.IntegerField)
    def get_total_orders(self, obj):
        return obj.orders.count()


class DashboardCashHandoverSerializer(serializers.ModelSerializer):
    """Master's cash handover request (Naqd topshirish) for admin review."""

    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = WithdrawRequest
        fields = (
            "id",
            "master",
            "master_detail",
            "amount",
            "status",
            "status_label",
            "admin_note",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DashboardCashHandoverActionSerializer(serializers.Serializer):
    """Request body: naqd topshirishni qabul qilish / rad etish uchun ixtiyoriy admin izohi."""

    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text=(
            "Admin izohi (ixtiyoriy). Bo'sh qoldirilsa default yoziladi: qabul qilishda "
            "'Naqd qabul qilindi', rad etishda 'Rad etildi'."
        ),
    )


class DashboardCashHandoverEnvelopeSerializer(serializers.Serializer):
    """`{success, message, data}` javob konverti; `data` — yangilangan naqd topshirish obyekti.

    Faqat OpenAPI hujjati uchun: `data` maydonini `@extend_schema_field` orqali
    :class:`DashboardCashHandoverSerializer` sifatida turlaydi.
    """

    success = serializers.BooleanField(default=True)
    message = serializers.CharField(default="OK")
    data = serializers.SerializerMethodField()

    @extend_schema_field(DashboardCashHandoverSerializer)
    def get_data(self, obj):
        return DashboardCashHandoverSerializer(obj, context=self.context).data


class DashboardMasterBlockSerializer(serializers.Serializer):
    """Block or unblock a master (optionally with a reason)."""

    is_blocked = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def save(self, **kwargs):
        master = self.context["master"]
        if self.validated_data["is_blocked"]:
            master.block(reason=self.validated_data.get("reason", ""))
        else:
            master.unblock()
        master.save()
        return master


class DashboardMasterApplicationSerializer(serializers.ModelSerializer):
    """Lean serializer for reviewing masters who left a registration application."""

    full_name = serializers.CharField(read_only=True)
    approval_status_label = serializers.CharField(source="get_approval_status_display", read_only=True)

    class Meta:
        model = Master
        fields = (
            "id",
            "phone",
            "first_name",
            "last_name",
            "full_name",
            "specialization",
            "avatar",
            "language",
            "approval_status",
            "approval_status_label",
            "approved_at",
            "rejected_reason",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class DashboardMasterSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    status = serializers.SerializerMethodField(help_text="Dashboard status: active, busy, inactive, blocked.")
    status_label = serializers.SerializerMethodField()
    approval_status_label = serializers.CharField(source="get_approval_status_display", read_only=True)
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        style={"input_type": "password"},
        help_text="Admin usta uchun parol o'rnatadi (tasdiqlashda). Faqat yozish uchun.",
    )
    orders_count = serializers.SerializerMethodField()
    completed_orders_count = serializers.SerializerMethodField()
    total_income = serializers.SerializerMethodField()

    class Meta:
        model = Master
        fields = (
            "id",
            "phone",
            "first_name",
            "last_name",
            "full_name",
            "specialization",
            "daraja",
            "address",
            "avatar",
            "rating",
            "status",
            "status_label",
            "approval_status",
            "approval_status_label",
            "approved_at",
            "rejected_reason",
            "password",
            "is_online",
            "is_available",
            "is_blocked",
            "blocked_at",
            "block_reason",
            "lat",
            "lng",
            "last_location_at",
            "language",
            "notifications_enabled",
            "push_enabled",
            "is_active",
            "orders_count",
            "completed_orders_count",
            "total_income",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "full_name",
            "rating",
            "status",
            "status_label",
            "approval_status_label",
            "approved_at",
            "blocked_at",
            "last_location_at",
            "orders_count",
            "completed_orders_count",
            "total_income",
            "created_at",
            "updated_at",
        )

    def update(self, instance, validated_data):
        # Admin tasdiqlash oqimi: parol o'rnatish + approval_status boshqaruvi.
        password = validated_data.pop("password", None)
        approval_status = validated_data.get("approval_status")
        if approval_status == MasterApprovalStatus.APPROVED:
            instance.is_active = True
            instance.approved_at = timezone.now()
            instance.rejected_reason = ""
        elif approval_status == MasterApprovalStatus.REJECTED:
            instance.is_active = False
            instance.approved_at = None
        if password:
            instance.set_password(password)  # pbkdf2 hash — save() qayta hash qilmaydi
        return super().update(instance, validated_data)

    @extend_schema_field(serializers.CharField)
    def get_status(self, obj):
        if obj.is_blocked or not obj.is_active:
            return "blocked"
        if obj.is_online and obj.is_available:
            return "active"
        if obj.is_online and not obj.is_available:
            return "busy"
        return "inactive"

    @extend_schema_field(serializers.CharField)
    def get_status_label(self, obj):
        labels = {"active": "Faol", "busy": "Band", "inactive": "Offline", "blocked": "Bloklangan"}
        return labels[self.get_status(obj)]

    @extend_schema_field(serializers.IntegerField)
    def get_orders_count(self, obj):
        return getattr(obj, "orders_count", obj.orders.count())

    @extend_schema_field(serializers.IntegerField)
    def get_completed_orders_count(self, obj):
        return getattr(obj, "completed_orders_count", obj.orders.filter(status=OrderStatus.COMPLETED).count())

    @extend_schema_field(serializers.DecimalField(max_digits=14, decimal_places=2))
    def get_total_income(self, obj):
        value = obj.orders.filter(status=OrderStatus.COMPLETED).aggregate(total=Sum("total_amount"))["total"]
        return value or 0


class DashboardMasterStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(("active", "Faol"), ("busy", "Band"), ("inactive", "Offline"), ("blocked", "Bloklangan")),
        help_text="active -> online/available, busy -> online/not available, inactive -> offline, blocked -> is_active False.",
    )

    def save(self, **kwargs):
        master = kwargs["master"]
        status = self.validated_data["status"]
        if status == "active":
            master.is_active = True
            master.is_online = True
            master.is_available = True
        elif status == "busy":
            master.is_active = True
            master.is_online = True
            master.is_available = False
        elif status == "inactive":
            master.is_active = True
            master.is_online = False
            master.is_available = False
        else:
            master.is_active = False
            master.is_online = False
            master.is_available = False
        master.save(update_fields=["is_active", "is_online", "is_available", "updated_at"])
        return master


class DashboardMasterLocationSerializer(serializers.Serializer):
    lat = serializers.DecimalField(max_digits=10, decimal_places=8)
    lng = serializers.DecimalField(max_digits=11, decimal_places=8)
    is_online = serializers.BooleanField(required=False, default=True)
    is_available = serializers.BooleanField(required=False, default=True)

    def save(self, **kwargs):
        master = kwargs["master"]
        master.lat = self.validated_data["lat"]
        master.lng = self.validated_data["lng"]
        master.is_online = self.validated_data.get("is_online", True)
        master.is_available = self.validated_data.get("is_available", True)
        master.last_location_at = timezone.now()
        master.save(update_fields=["lat", "lng", "is_online", "is_available", "last_location_at", "updated_at"])
        return master


class DashboardOrderTrackingSerializer(serializers.ModelSerializer):
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


class DashboardOrderSerializer(serializers.ModelSerializer):
    code = serializers.SerializerMethodField(help_text="Frontend uchun qisqa order code: ORD-XXXXXXXX.")
    client_detail = DashboardClientMiniSerializer(source="client", read_only=True)
    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)
    service_detail = DashboardServiceMiniSerializer(source="service", read_only=True)
    tracking = DashboardOrderTrackingSerializer(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    status_tab = serializers.SerializerMethodField(
        help_text="Figma tab/badge bucket: yangi / yo'lda / bajarilmoqda / yakunlangan / bekor."
    )
    payment_type_label = serializers.CharField(source="get_payment_type_display", read_only=True)
    assigned_masters = serializers.SerializerMethodField(help_text="Orderga biriktirilgan ustalar (Figma 'Usta' ustuni).")
    masters_count = serializers.SerializerMethodField(help_text="Biriktirilgan ustalar soni (Figma badge).")
    assistants = serializers.SerializerMethodField(help_text="Orderga biriktirilgan shogirdlar (Figma 'Shogird' ustuni).")
    assistants_count = serializers.SerializerMethodField(help_text="Biriktirilgan shogirdlar soni (Figma badge).")
    can_cancel = serializers.SerializerMethodField(help_text="Frontend cancel button ko'rsatishi mumkinmi.")
    can_rate = serializers.SerializerMethodField(help_text="Frontend rating button/modal ko'rsatishi mumkinmi.")
    time = serializers.SerializerMethodField(help_text="created_at dan HH:MM format.")
    address_text = serializers.CharField(required=False)
    lat = serializers.DecimalField(max_digits=10, decimal_places=8, required=False)
    lng = serializers.DecimalField(max_digits=11, decimal_places=8, required=False)

    class Meta:
        model = Order
        fields = (
            "id",
            "code",
            "client",
            "client_detail",
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
            "status_label",
            "status_tab",
            "payment_type",
            "payment_type_label",
            "assigned_masters",
            "masters_count",
            "assistants",
            "assistants_count",
            "service_fee",
            "inventory_total",
            "bonus_used",
            "total_amount",
            "before_photo",
            "completion_photo",
            "completion_note",
            "cancel_reason",
            "rejected_reason",
            "tracking",
            "can_cancel",
            "can_rate",
            "time",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "code",
            "client_detail",
            "master_detail",
            "service_detail",
            "status_label",
            "status_tab",
            "payment_type_label",
            "assigned_masters",
            "masters_count",
            "assistants",
            "assistants_count",
            "tracking",
            "can_cancel",
            "can_rate",
            "time",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "status": {"help_text": "`new`, `accepted`, `on_way`, `arrived`, `completed`, `cancelled`, `rejected`."},
            "payment_type": {"help_text": "`cash`, `online`, `card`, `plastic`."},
            "service_fee": {"help_text": "Service narxi. Berilmasa service.base_price olinadi."},
            "inventory_total": {"help_text": "Usta ishlatgan mahsulotlar jami."},
            "bonus_used": {"help_text": "Client ishlatgan bonus summa."},
            "total_amount": {"help_text": "service_fee + inventory_total - bonus_used."},
        }

    @extend_schema_field(serializers.CharField)
    def get_code(self, obj):
        return f"ORD-{str(obj.id).split('-')[0].upper()}"

    @extend_schema_field(serializers.CharField)
    def get_status_tab(self, obj):
        return STATUS_TAB.get(obj.status, obj.status)

    def _active_assigned(self, obj):
        # Uses the prefetched reverse manager when available to avoid N+1.
        return [om for om in obj.assigned_masters.all() if om.is_active]

    @extend_schema_field(DashboardMasterMiniSerializer(many=True))
    def get_assigned_masters(self, obj):
        masters = [om.master for om in self._active_assigned(obj)]
        return DashboardMasterMiniSerializer(masters, many=True).data

    @extend_schema_field(serializers.IntegerField)
    def get_masters_count(self, obj):
        return len(self._active_assigned(obj))

    def _active_assistants(self, obj):
        return [a for a in obj.dashboard_assistants.all() if a.is_active]

    @extend_schema_field(DashboardMasterMiniSerializer(many=True))
    def get_assistants(self, obj):
        assistants = [a.assistant for a in self._active_assistants(obj)]
        return DashboardMasterMiniSerializer(assistants, many=True).data

    @extend_schema_field(serializers.IntegerField)
    def get_assistants_count(self, obj):
        return len(self._active_assistants(obj))

    @extend_schema_field(serializers.BooleanField)
    def get_can_cancel(self, obj):
        return obj.status in {OrderStatus.NEW, OrderStatus.ACCEPTED, OrderStatus.ON_WAY}

    @extend_schema_field(serializers.BooleanField)
    def get_can_rate(self, obj):
        return obj.status == OrderStatus.COMPLETED and not hasattr(obj, "review")

    @extend_schema_field(serializers.CharField)
    def get_time(self, obj):
        return timezone.localtime(obj.created_at).strftime("%H:%M")

    def validate_status(self, value):
        # Block completing (or reviving a terminal order) via the generic order write —
        # completion must run the master flow that credits the wallet + deducts inventory.
        current = getattr(self.instance, "status", OrderStatus.NEW)
        if not can_admin_set_status(current, value):
            raise serializers.ValidationError(
                "Bu holat o'zgarishiga ruxsat yo'q. Yakunlash usta yakunlash oqimi orqali bo'ladi."
            )
        return value

    def validate(self, attrs):
        client = attrs.get("client") or getattr(self.instance, "client", None)
        address = attrs.get("address") or getattr(self.instance, "address", None)
        if address and client and address.client_id != client.id:
            raise serializers.ValidationError({"address": "Address shu clientga tegishli emas"})
        if address:
            attrs.setdefault("address_text", address.address_text)
            attrs.setdefault("lat", address.lat)
            attrs.setdefault("lng", address.lng)
        if self.instance is None:
            missing = [field for field in ("address_text", "lat", "lng") if field not in attrs]
            if missing:
                raise serializers.ValidationError({field: "Bu field kerak yoki address yuboring" for field in missing})
        return attrs

    def create(self, validated_data):
        # service_fee is entered by the master at check time, not taken from the service
        # catalog. An admin may still pass service_fee explicitly; otherwise it stays 0.
        order = Order(**validated_data)
        order.recalculate_total()
        order.save()
        ensure_tracking(order)
        return order

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if {"service_fee", "inventory_total", "bonus_used", "service"} & set(validated_data):
            instance.recalculate_total()
        instance.save()
        ensure_tracking(instance)
        return instance


class DashboardOrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices, help_text="Order status qiymati.")
    cancel_reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
    rejected_reason = serializers.CharField(max_length=255, required=False, allow_blank=True)

    @transaction.atomic
    def save(self, **kwargs):
        # Lock the row and guard the transition: completing must go through the master
        # completion flow (wallet credit + inventory), and a terminal order can't be revived.
        order = Order.objects.select_for_update().get(pk=kwargs["order"].pk)
        new_status = self.validated_data["status"]
        if not can_admin_set_status(order.status, new_status):
            raise serializers.ValidationError(
                {"status": "Bu holat o'zgarishiga ruxsat yo'q. Yakunlash usta yakunlash oqimi orqali bo'ladi."}
            )
        order.status = new_status
        if order.status == OrderStatus.CANCELLED:
            order.cancel_reason = self.validated_data.get("cancel_reason", order.cancel_reason)
        if order.status == OrderStatus.REJECTED:
            order.rejected_reason = self.validated_data.get("rejected_reason", order.rejected_reason)
        order.save(update_fields=["status", "cancel_reason", "rejected_reason", "updated_at"])
        ensure_tracking(order)
        return order


class DashboardOrderAssignSerializer(serializers.Serializer):
    """Assign masters (Usta) and/or assistants (Shogird) to an order.

    Both Figma modals ("Usta biriktirish" / "Shogird biriktirish") send the full
    selection on Saqlash, so each provided list REPLACES the current active set.
    Only the keys that are present are touched. Assignment does NOT change the
    order status — the order stays `new` until a master accepts.
    """

    masters = serializers.PrimaryKeyRelatedField(
        queryset=Master.objects.filter(is_active=True),
        many=True,
        required=False,
        help_text="Biriktiriladigan usta id'lari (to'liq tanlov).",
    )
    assistants = serializers.PrimaryKeyRelatedField(
        queryset=Master.objects.filter(is_active=True),
        many=True,
        required=False,
        help_text="Biriktiriladigan shogird id'lari (to'liq tanlov).",
    )
    master = serializers.PrimaryKeyRelatedField(
        queryset=Master.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        help_text="(Eski, ixtiyoriy) bitta usta. `masters` ro'yxati afzal.",
    )

    def validate(self, attrs):
        if not any(key in self.initial_data for key in ("masters", "assistants", "master")):
            raise serializers.ValidationError("`masters`, `assistants` yoki `master` yuboring")
        return attrs

    def _admin(self):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return user if getattr(user, "is_authenticated", False) else None

    @staticmethod
    def _sync_set(order, related_name, master_field, wanted, admin):
        """Replace the active related set (OrderMaster / DashboardOrderAssistant)."""
        wanted_ids = {m.id for m in wanted}
        existing = {getattr(row, f"{master_field}_id"): row for row in getattr(order, related_name).all()}
        for master_id, row in existing.items():
            if master_id not in wanted_ids and row.is_active:
                row.is_active = False
                row.save(update_fields=["is_active", "updated_at"])
        created = []
        manager = getattr(order, related_name)
        for master in wanted:
            row = existing.get(master.id)
            if row is None:
                manager.create(**{master_field: master, "assigned_by": admin})
                created.append(master)
            elif not row.is_active:
                row.is_active = True
                row.assigned_by = admin
                row.save(update_fields=["is_active", "assigned_by", "updated_at"])
                created.append(master)
        return created

    def save(self, **kwargs):
        order = kwargs["order"]
        admin = self._admin()

        masters = self.validated_data.get("masters")
        if masters is None and self.validated_data.get("master") is not None:
            masters = [self.validated_data["master"]]

        previous_master_ids = None
        if masters is not None:
            previous_master_ids = set(
                order.assigned_masters.filter(is_active=True).values_list("master_id", flat=True)
            )

        newly_assigned = []
        if masters is not None:
            newly_assigned += self._sync_set(order, "assigned_masters", "master", masters, admin)
        if "assistants" in self.validated_data:
            self._sync_set(order, "dashboard_assistants", "assistant", self.validated_data["assistants"], admin)

        ensure_tracking(order)
        for master in newly_assigned:
            create_notification(
                role="master",
                master=master,
                title="Yangi buyurtma biriktirildi",
                body=order.address_text,
                data={"order_id": str(order.id), "status": order.status},
            )
        order.refresh_from_db()
        if previous_master_ids is not None:
            current_master_ids = set(
                order.assigned_masters.filter(is_active=True).values_list("master_id", flat=True)
            )
            if previous_master_ids != current_master_ids:
                broadcast_dashboard_order(order, "order.master_changed")
        return order


class DashboardNotificationSerializer(serializers.ModelSerializer):
    client_detail = DashboardClientMiniSerializer(source="client", read_only=True)
    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "role",
            "client",
            "client_detail",
            "master",
            "master_detail",
            "title",
            "body",
            "data",
            "is_read",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "client_detail", "master_detail", "created_at", "updated_at")
        extra_kwargs = {"is_read": {"help_text": "true bo'lsa notification o'qilgan."}}

    def validate(self, attrs):
        role = attrs.get("role") or getattr(self.instance, "role", None)
        client = attrs.get("client") or getattr(self.instance, "client", None)
        master = attrs.get("master") or getattr(self.instance, "master", None)
        if role == "client" and not client:
            raise serializers.ValidationError({"client": "Client notification uchun client kerak"})
        if role == "master" and not master:
            raise serializers.ValidationError({"master": "Master notification uchun master kerak"})
        return attrs


class DashboardExpenseSerializer(serializers.ModelSerializer):
    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)

    class Meta:
        model = MasterExpense
        fields = (
            "id",
            "master",
            "master_detail",
            "purpose",
            "name",
            "amount",
            "date",
            "product_name",
            "price",
            "quantity",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "master_detail", "created_at", "updated_at")


class DashboardStaffProfileSerializer(serializers.ModelSerializer):
    role = serializers.CharField(required=False, max_length=30)
    role_label = serializers.SerializerMethodField()
    permissions_count = serializers.SerializerMethodField()
    permissions_display = serializers.SerializerMethodField()
    permissions_label = serializers.SerializerMethodField()

    class Meta:
        model = DashboardStaffProfile
        fields = (
            "role",
            "role_label",
            "phone",
            "permissions",
            "permissions_count",
            "permissions_display",
            "permissions_label",
        )
        read_only_fields = ("role_label", "permissions_count", "permissions_display", "permissions_label")

    def validate_role(self, value):
        value = str(value).strip()
        if not value:
            raise serializers.ValidationError("Rol bo'sh bo'lishi mumkin emas")
        return value

    @extend_schema_field(serializers.CharField)
    def get_role_label(self, obj):
        return dashboard_role_label(obj.role)

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_permissions_count(self, obj):
        user = getattr(obj, "user", None)
        return dashboard_permissions_payload(obj, user)["permissions_count"]

    @extend_schema_field(serializers.CharField)
    def get_permissions_display(self, obj):
        user = getattr(obj, "user", None)
        return dashboard_permissions_payload(obj, user)["permissions_display"]

    @extend_schema_field(serializers.CharField)
    def get_permissions_label(self, obj):
        user = getattr(obj, "user", None)
        return dashboard_permissions_payload(obj, user)["permissions_label"]


class DashboardStaffSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    role_label = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    permissions_count = serializers.SerializerMethodField()
    permissions_display = serializers.SerializerMethodField()
    permissions_label = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    profile = DashboardStaffProfileSerializer(source="dashboard_profile", required=False)

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "avatar",
            "email",
            "password",
            "is_staff",
            "is_superuser",
            "is_active",
            "last_login",
            "date_joined",
            "role",
            "role_label",
            "phone",
            "permissions",
            "permissions_count",
            "permissions_display",
            "permissions_label",
            "profile",
        )
        read_only_fields = ("id", "full_name", "last_login", "date_joined")

    @extend_schema_field(serializers.CharField)
    def get_full_name(self, obj):
        return obj.get_full_name() or obj.get_username()

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_avatar(self, obj):
        return None

    def get_profile(self, obj):
        try:
            return obj.dashboard_profile
        except DashboardStaffProfile.DoesNotExist:
            return None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_role(self, obj):
        profile = self.get_profile(obj)
        return profile.role if profile else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_role_label(self, obj):
        profile = self.get_profile(obj)
        return dashboard_role_label(profile.role) if profile else None

    @extend_schema_field(serializers.CharField)
    def get_phone(self, obj):
        profile = self.get_profile(obj)
        return profile.phone if profile else ""

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_permissions(self, obj):
        profile = self.get_profile(obj)
        return dashboard_permissions_payload(profile, obj)["permissions"] if profile else []

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_permissions_count(self, obj):
        profile = self.get_profile(obj)
        return dashboard_permissions_payload(profile, obj)["permissions_count"] if profile else 0

    @extend_schema_field(serializers.CharField)
    def get_permissions_display(self, obj):
        profile = self.get_profile(obj)
        return dashboard_permissions_payload(profile, obj)["permissions_display"] if profile else "0-ta bo'lim"

    @extend_schema_field(serializers.CharField)
    def get_permissions_label(self, obj):
        profile = self.get_profile(obj)
        return dashboard_permissions_payload(profile, obj)["permissions_label"] if profile else ""

    def to_internal_value(self, data):
        data = data.copy()
        full_name = str(data.get("full_name") or "").strip()
        if full_name and not data.get("first_name"):
            first_name, _, last_name = full_name.partition(" ")
            data["first_name"] = first_name
            if last_name and not data.get("last_name"):
                data["last_name"] = last_name
        return super().to_internal_value(data)

    def create(self, validated_data):
        profile_data = validated_data.pop("dashboard_profile", {})
        password = validated_data.pop("password", None)
        validated_data["is_staff"] = True
        user = get_user_model().objects.create_user(password=password or None, **validated_data)
        DashboardStaffProfile.objects.create(user=user, **profile_data)
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("dashboard_profile", None)
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if profile_data is not None:
            profile, _ = DashboardStaffProfile.objects.get_or_create(user=instance)
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()
        return instance


class DashboardOrderAssistantSerializer(serializers.ModelSerializer):
    assistant_detail = DashboardMasterMiniSerializer(source="assistant", read_only=True)
    assigned_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DashboardOrderAssistant
        fields = (
            "id",
            "order",
            "assistant",
            "assistant_detail",
            "assigned_by",
            "assigned_by_name",
            "note",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "order", "assigned_by", "assigned_by_name", "created_at", "updated_at")

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_assigned_by_name(self, obj):
        return obj.assigned_by.get_full_name() or obj.assigned_by.get_username() if obj.assigned_by else None


class DashboardLiveStreamSerializer(serializers.ModelSerializer):
    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)
    client_detail = DashboardClientMiniSerializer(source="client", read_only=True)
    order_code = serializers.SerializerMethodField()
    duration_label = serializers.SerializerMethodField()

    class Meta:
        model = DashboardLiveStream
        fields = (
            "id",
            "title",
            "service_name",
            "master",
            "master_detail",
            "client",
            "client_detail",
            "order",
            "order_code",
            "stream_url",
            "archive_url",
            "thumbnail",
            "status",
            "started_at",
            "ended_at",
            "duration_seconds",
            "duration_label",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "order_code", "duration_label", "created_at", "updated_at")

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_order_code(self, obj):
        return f"ORD-{str(obj.order_id).split('-')[0].upper()}" if obj.order_id else None

    @extend_schema_field(serializers.CharField)
    def get_duration_label(self, obj):
        minutes, seconds = divmod(obj.duration_seconds or 0, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    def validate(self, attrs):
        order = attrs.get("order") or getattr(self.instance, "order", None)
        if order:
            attrs.setdefault("client", order.client)
            attrs.setdefault("master", order.master)
            attrs.setdefault("service_name", order.service.name)
        return attrs


class DashboardCompanyExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardCompanyExpense
        fields = ("id", "purpose", "name", "amount", "date", "note", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class DashboardWarehouseExpenseSerializer(serializers.ModelSerializer):
    product_detail = serializers.SerializerMethodField()

    class Meta:
        model = DashboardWarehouseExpense
        fields = (
            "id",
            "product",
            "product_detail",
            "purpose",
            "name",
            "amount",
            "date",
            "price",
            "quantity",
            "note",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "product_detail", "created_at", "updated_at")

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_product_detail(self, obj):
        if not obj.product:
            return None
        return {"id": obj.product.id, "name": obj.product.name, "unit": obj.product.unit}


class DashboardIntegrationSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardIntegrationSetting
        fields = ("id", "key", "title", "value", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class DashboardBackupSerializer(serializers.ModelSerializer):
    size_human = serializers.SerializerMethodField(help_text="O'qishga qulay hajm (KB/MB/GB).")
    download_url = serializers.SerializerMethodField(help_text="`.sql` faylni yuklab olish havolasi.")
    exists = serializers.BooleanField(read_only=True, help_text="Fayl diskda mavjudmi.")

    class Meta:
        model = DashboardBackup
        fields = (
            "id",
            "filename",
            "size_bytes",
            "size_human",
            "engine",
            "source",
            "note",
            "exists",
            "download_url",
            "created_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.CharField)
    def get_size_human(self, obj):
        size = float(obj.size_bytes or 0)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @extend_schema_field(serializers.CharField)
    def get_download_url(self, obj):
        request = self.context.get("request")
        url = reverse("dashboard-backup-download", args=[obj.id])
        return request.build_absolute_uri(url) if request else url


class DashboardBackupSettingsSerializer(serializers.Serializer):
    """Avtomatik backup sozlamalari (haftalik). DashboardIntegrationSetting'da saqlanadi."""

    enabled = serializers.BooleanField(required=False, help_text="Avtomatik backup yoqilganmi.")
    frequency = serializers.ChoiceField(choices=("weekly",), required=False, help_text="Hozircha `weekly`.")
    day_of_week = serializers.IntegerField(min_value=0, max_value=6, required=False, help_text="0=Yakshanba ... 1=Dushanba.")
    hour = serializers.IntegerField(min_value=0, max_value=23, required=False)
    keep = serializers.IntegerField(min_value=1, max_value=365, required=False, allow_null=True, help_text="Nechta backup saqlansin.")


class DashboardMarketCategorySerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = MarketCategory
        fields = ("id", "name", "slug", "products_count", "created_at", "updated_at")
        read_only_fields = ("id", "products_count", "created_at", "updated_at")

    @extend_schema_field(serializers.IntegerField)
    def get_products_count(self, obj):
        return getattr(obj, "products_count", obj.marketproduct_set.count())


class DashboardMarketProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketProductImage
        fields = ("id", "product", "image", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


@extend_schema_field(OpenApiTypes.BINARY)
class _UploadImageField(serializers.ImageField):
    """ImageField that Swagger renders as a file upload (format: binary), not a URI."""


class DashboardMarketProductSerializer(serializers.ModelSerializer):
    category_detail = DashboardMarketCategorySerializer(source="category", read_only=True)
    seller_detail = DashboardClientMiniSerializer(source="seller", read_only=True)
    images = DashboardMarketProductImageSerializer(many=True, read_only=True)
    uploaded_images = serializers.ListField(
        child=_UploadImageField(),
        write_only=True,
        required=False,
        help_text="Bitta so'rovda mahsulot bilan birga yuklanadigan rasmlar (alohida image API shart emas).",
    )
    orders_count = serializers.SerializerMethodField()

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
            "uploaded_images",
            "orders_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "category_detail", "seller_detail", "images", "orders_count", "created_at", "updated_at")

    @extend_schema_field(serializers.IntegerField)
    def get_orders_count(self, obj):
        return getattr(obj, "orders_count", obj.orders.count())

    @staticmethod
    def _save_images(product, images):
        if images:
            MarketProductImage.objects.bulk_create(
                [MarketProductImage(product=product, image=image) for image in images]
            )

    def create(self, validated_data):
        images = validated_data.pop("uploaded_images", [])
        product = super().create(validated_data)
        self._save_images(product, images)
        return product

    def update(self, instance, validated_data):
        images = validated_data.pop("uploaded_images", [])
        product = super().update(instance, validated_data)
        self._save_images(product, images)
        return product


class DashboardMarketOrderSerializer(serializers.ModelSerializer):
    client_detail = DashboardClientMiniSerializer(source="client", read_only=True)
    product_detail = DashboardMarketProductSerializer(source="product", read_only=True)

    class Meta:
        model = MarketOrder
        fields = (
            "id",
            "client",
            "client_detail",
            "product",
            "product_detail",
            "quantity",
            "delivery_address",
            "phone",
            "note",
            "total_amount",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "client_detail", "product_detail", "total_amount", "created_at", "updated_at")

    def create(self, validated_data):
        # Reserve stock (locked, validated) — same path as the client order flow.
        return place_market_order(**validated_data)


class DashboardWarehouseCategorySerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = WarehouseCategory
        fields = ("id", "name", "slug", "products_count", "created_at", "updated_at")
        read_only_fields = ("id", "products_count", "created_at", "updated_at")

    @extend_schema_field(serializers.IntegerField)
    def get_products_count(self, obj):
        return getattr(obj, "products_count", obj.products.count())


class DashboardWarehouseProductSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)
    movements_count = serializers.SerializerMethodField()
    category_detail = DashboardWarehouseCategorySerializer(source="category", read_only=True)
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
            "is_active",
            "is_low_stock",
            "movements_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "is_low_stock", "movements_count", "stock_value", "created_at", "updated_at")

    @extend_schema_field(serializers.IntegerField)
    def get_movements_count(self, obj):
        return getattr(obj, "movements_count", obj.movements.count())


class DashboardStockMovementSerializer(serializers.ModelSerializer):
    product_detail = DashboardWarehouseProductSerializer(source="product", read_only=True)
    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)

    class Meta:
        model = StockMovement
        fields = (
            "id",
            "product",
            "product_detail",
            "movement_type",
            "quantity",
            "note",
            "master",
            "master_detail",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "product_detail", "master_detail", "created_at", "updated_at")


class DashboardMasterInventorySerializer(serializers.ModelSerializer):
    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)
    product_detail = DashboardWarehouseProductSerializer(source="warehouse_product", read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = MasterInventory
        fields = (
            "id",
            "master",
            "master_detail",
            "warehouse_product",
            "product_detail",
            "quantity",
            "unit",
            "low_threshold",
            "image",
            "is_low_stock",
            "assigned_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "master_detail", "product_detail", "is_low_stock", "assigned_at", "created_at", "updated_at")


class DashboardMasterInventoryAssignSerializer(serializers.Serializer):
    """Ustaga mahsulot biriktirish (write). Ombordan ayiradi, StockMovement yozadi,
    mavjud biriktirishni to'ldiradi — :func:`assign_inventory_to_master` orqali."""

    master = serializers.PrimaryKeyRelatedField(queryset=Master.objects.all())
    warehouse_product = serializers.PrimaryKeyRelatedField(
        queryset=WarehouseProduct.objects.filter(is_active=True)
    )
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    def save(self, **kwargs):
        return assign_inventory_to_master(
            master=self.validated_data["master"],
            product=self.validated_data["warehouse_product"],
            quantity=self.validated_data["quantity"],
        )


class DashboardSupportMessageSerializer(serializers.ModelSerializer):
    client_detail = DashboardClientMiniSerializer(source="client", read_only=True)
    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)

    class Meta:
        model = SupportMessage
        fields = (
            "id",
            "sender_role",
            "client",
            "client_detail",
            "master",
            "master_detail",
            "message",
            "attachment",
            "is_read",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "client_detail", "master_detail", "created_at", "updated_at")


class DashboardMasterWalletSerializer(serializers.ModelSerializer):
    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)
    total_balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = MasterWallet
        fields = (
            "id",
            "master",
            "master_detail",
            "balance_online",
            "balance_cash",
            "total_balance",
            "total_earned",
            "total_withdrawn",
            "created_at",
            "updated_at",
        )
        # Balances are only ever moved through the wallet services (order completion,
        # cash handover, manual transaction) — never edited directly on the wallet.
        read_only_fields = (
            "id",
            "master_detail",
            "balance_online",
            "balance_cash",
            "total_earned",
            "total_withdrawn",
            "created_at",
            "updated_at",
        )


class DashboardWalletTransactionSerializer(serializers.ModelSerializer):
    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)

    class Meta:
        model = WalletTransaction
        fields = (
            "id",
            "master",
            "master_detail",
            "transaction_type",
            "amount",
            "description",
            "payment_method",
            "order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "master_detail", "created_at", "updated_at")


class DashboardWithdrawRequestSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    master_detail = DashboardMasterMiniSerializer(source="master", read_only=True)

    class Meta:
        model = WithdrawRequest
        fields = ("id", "master", "master_detail", "amount", "status", "admin_note", "created_at", "updated_at")
        read_only_fields = ("id", "master_detail", "created_at", "updated_at")
