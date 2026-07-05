from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view
from django.utils import timezone
from rest_framework import generics, permissions

from apps.accounts.models import Client, FCMDevice, Master
from apps.accounts.permissions import IsClient, IsMaster
from apps.accounts.serializers import (
    ClientRegisterSerializer,
    ClientSerializer,
    FCMDeviceSerializer,
    LanguageSerializer,
    LogoutSerializer,
    MasterLoginSerializer,
    MasterProfileSerializer,
    MasterRegisterSerializer,
    RefreshSerializer,
    SendOTPSerializer,
    VerifyOTPSerializer,
)
from apps.common.responses import success_response
from apps.common.views import EnvelopeMixin


def app_language_items(active_code="uz"):
    return [
        {"code": "uz", "label": "O'zbekcha", "is_active": active_code == "uz"},
        {"code": "ru", "label": "Russkiy", "is_active": active_code == "ru"},
        {"code": "en", "label": "English", "is_active": active_code == "en"},
    ]


CLIENT_PROFILE_RESPONSE_EXAMPLE = {
    "success": True,
    "message": "OK",
    "data": {
        "id": "8df2d8b5-2e3b-4d6e-8a1c-3e8f54d2e3a1",
        "phone": "+998901234567",
        "first_name": "Aziz",
        "last_name": "Karimov",
        "avatar": None,
        "language": "uz",
        "notifications_enabled": True,
        "push_enabled": True,
        "current_tariff": "Premium",
        "tariff_expires_at": "2026-07-25T10:00:00+05:00",
        "addresses_count": 3,
        "total_spent": "0.00",
        "total_orders": 0,
    },
}


@extend_schema(
    tags=["Master Auth"],
    summary="Master login",
    description=(
        "Master phone + password orqali login qiladi. Response ichidagi `access_token` ni Swagger Authorize "
        "oynasiga kiriting. `refresh_token` 15 kunlik va refresh endpointda yangi tokenlar olish uchun ishlatiladi."
    ),
    examples=[
        OpenApiExample(
            "Master login request",
            value={"phone": "+998901112233", "password": "1234"},
            request_only=True,
        ),
        OpenApiExample(
            "Master login success",
            value={
                "success": True,
                "message": "OK",
                "data": {
                    "access_token": "eyJ...",
                    "refresh_token": "eyJ...",
                    "expires_in": 259200,
                    "master": {"id": "uuid", "full_name": "Ali Usta", "phone": "+998901112233"},
                },
            },
            response_only=True,
        ),
    ],
)
class MasterLoginView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = MasterLoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.save())


@extend_schema(
    tags=["Master Auth"],
    summary="Master ariza qoldirish",
    description=(
        "Usta appga birinchi kirganda ism, familiya va telefon raqamini qoldiradi. Ariza `pending` holatda "
        "yaratiladi. Admin tasdiqlab password bergandan keyin `POST /master/auth/login/` ishlaydi."
    ),
    examples=[
        OpenApiExample(
            "Master register request",
            value={
                "first_name": "Ali",
                "last_name": "Karimov",
                "phone": "+998901112233",
                "specialization": "Konditsioner ustasi",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Master register success",
            value={
                "success": True,
                "message": "Arizangiz qabul qilindi. Admin tasdiqlagandan keyin login parol beriladi.",
                "data": {
                    "id": "uuid",
                    "first_name": "Ali",
                    "last_name": "Karimov",
                    "phone": "+998901112233",
                    "specialization": "Konditsioner ustasi",
                    "approval_status": "pending",
                    "created_at": "2026-06-27T10:00:00+05:00",
                },
            },
            response_only=True,
        ),
    ],
)
class MasterRegisterView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = MasterRegisterSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(
            serializer.data,
            message="Arizangiz qabul qilindi. Admin tasdiqlagandan keyin login parol beriladi.",
            status=201,
        )


@extend_schema(
    tags=["Master Auth"],
    summary="Master access tokenni yangilash",
    description="Eski `refresh_token` yuboriladi. Response yangi `access_token` va yangi `refresh_token` qaytaradi.",
    examples=[OpenApiExample("Refresh request", value={"refresh_token": "eyJ..."}, request_only=True)],
)
class MasterRefreshView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = RefreshSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.save())


@extend_schema(tags=["Master Auth"])
class MasterLogoutView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = LogoutSerializer

    def post(self, request):
        return success_response(message="Logged out")


@extend_schema(tags=["Master Auth"])
class MasterMeView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterProfileSerializer

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Master Auth"])
class MasterLanguageView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = LanguageSerializer

    def put(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.language = serializer.validated_data["language"]
        request.user.save(update_fields=["language"])
        return success_response({"language": request.user.language})


@extend_schema(
    tags=["Client Auth"],
    summary="Clientga OTP yuborish",
    description=(
        "Telefon raqamga OTP yuboradi. OTP TTL 120 sekund. Bitta telefon uchun qayta so'rov cooldown 3 daqiqa. "
        "5 marta noto'g'ri kod kiritilsa 15 daqiqa block bo'ladi."
    ),
    examples=[
        OpenApiExample("Send OTP request", value={"phone": "+998901234567"}, request_only=True),
        OpenApiExample("Send OTP success", value={"success": True, "message": "OK", "data": {"phone": "+998901234567", "expires_in": 120}}, response_only=True),
    ],
)
class SendOTPView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = SendOTPSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.save())


@extend_schema(
    tags=["Client Auth"],
    summary="OTP tasdiqlash va client token olish",
    description=(
        "OTP to'g'ri bo'lsa client uchun `access_token`, `refresh_token`, `is_new` va `client` ma'lumotlari qaytadi. "
        "`is_new=true` bo'lsa `PATCH /client/auth/register/` orqali profilni to'ldiring."
    ),
    examples=[
        OpenApiExample("Verify OTP request", value={"phone": "+998901234567", "otp_code": "123456"}, request_only=True),
        OpenApiExample(
            "Verify OTP success",
            value={
                "success": True,
                "message": "OK",
                "data": {
                    "access_token": "eyJ...",
                    "refresh_token": "eyJ...",
                    "expires_in": 259200,
                    "is_new": True,
                    "client": {"id": "uuid", "phone": "+998901234567", "first_name": "", "last_name": ""},
                },
            },
            response_only=True,
        ),
    ],
)
class VerifyOTPView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.save())


@extend_schema(
    tags=["Client Auth"],
    summary="Client profilini birinchi marta to'ldirish",
    description="OTP login bo'lgandan keyin `is_new=true` bo'lsa ishlatiladi. Authorization: client access token kerak.",
    examples=[
        OpenApiExample(
            "Client register request",
            value={"first_name": "Aziz", "last_name": "Karimov", "language": "uz"},
            request_only=True,
        )
    ],
)
class ClientRegisterView(EnvelopeMixin, generics.UpdateAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientRegisterSerializer

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Client Auth"])
class ClientRefreshView(MasterRefreshView):
    pass


@extend_schema(tags=["Client Auth"])
class ClientLogoutView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = LogoutSerializer

    def post(self, request):
        return success_response(message="Logged out")


@extend_schema(tags=["Client Auth"])
@extend_schema(tags=["Account"])
class DeleteAccountView(generics.GenericAPIView):
    serializer_class = LogoutSerializer

    def delete(self, request):
        request.user.delete()
        return success_response(message="Delete request accepted")


@extend_schema_view(
    get=extend_schema(
        tags=["Client Profile"],
        summary="Client profile screen ma'lumotlari",
        description=(
            "Profile page yuqori card va sozlamalar uchun ishlatiladi. `current_tariff` ID emas, tarif nomi "
            "sifatida qaytadi. `addresses_count` Profile sahifadagi `Manzillar 3` count uchun."
        ),
        examples=[OpenApiExample("Client profile response", value=CLIENT_PROFILE_RESPONSE_EXAMPLE, response_only=True)],
    ),
    put=extend_schema(
        tags=["Client Profile"],
        summary="Client profilini to'liq yangilash",
        description="Ism, familiya, avatar va language fieldlarini yangilash uchun.",
    ),
    patch=extend_schema(
        tags=["Client Profile"],
        summary="Client profilini qisman yangilash",
        description="Profile edit oynasi uchun. Masalan: `first_name`, `last_name`, `language`, `avatar`.",
    ),
)
class ClientProfileView(EnvelopeMixin, generics.RetrieveUpdateAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientSerializer

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Client App"], summary="Client app bootstrap")
class ClientAppBootstrapView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientSerializer

    def get(self, request):
        from django.db.models import Count

        from apps.market.models import MarketCategory
        from apps.market.serializers import MarketCategoryListSerializer
        from apps.notifications.models import Notification
        from apps.orders.models import Order, OrderStatus, PaymentType
        from apps.orders.serializers import OrderSerializer
        from apps.orders.views import get_home_banners
        from apps.profiles.models import Tariff
        from apps.profiles.serializers import ClientAddressSerializer, ClientDeviceSerializer, TariffSerializer
        from apps.services.models import ServiceCategory
        from apps.services.serializers import ServiceCategorySerializer

        active_orders = (
            Order.objects.filter(client=request.user)
            .exclude(status__in=[OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED])
            .select_related("service", "master", "tracking")[:5]
        )
        recent_orders = Order.objects.filter(client=request.user).select_related("service", "master", "tracking")[:5]
        data = {
            "profile": ClientSerializer(request.user).data,
            "home": {
                "banners": get_home_banners(request),
                "services": ServiceCategorySerializer(
                    ServiceCategory.objects.filter(is_active=True).prefetch_related("services__prices"),
                    many=True,
                    context={"request": request},
                ).data,
                "active_orders": OrderSerializer(active_orders, many=True, context={"request": request}).data,
                "recent_orders": OrderSerializer(recent_orders, many=True, context={"request": request}).data,
                "default_address": ClientAddressSerializer(
                    request.user.addresses.filter(is_default=True).first(), context={"request": request}
                ).data
                if request.user.addresses.filter(is_default=True).exists()
                else None,
            },
            "profile_sections": {
                "addresses_count": request.user.addresses.count(),
                "devices_count": request.user.client_devices.count(),
                "devices": ClientDeviceSerializer(
                    request.user.client_devices.select_related("address")[:5],
                    many=True,
                    context={"request": request},
                ).data,
                "tariffs": TariffSerializer(Tariff.objects.filter(is_active=True)[:6], many=True).data,
            },
            "market": {
                "categories": MarketCategoryListSerializer(
                    MarketCategory.objects.annotate(products_count=Count("marketproduct")).order_by("name")[:12],
                    many=True,
                ).data,
            },
            "counts": {
                "active_orders": len(active_orders),
                "unread_notifications": Notification.objects.filter(client=request.user, is_read=False).count(),
                "devices": request.user.client_devices.count(),
            },
            "choices": {
                "languages": app_language_items(request.user.language),
                "order_statuses": [{"value": value, "label": label} for value, label in OrderStatus.choices],
                "payment_types": [{"value": value, "label": label} for value, label in PaymentType.choices],
            },
            "navigation": [
                {"key": "home", "label": "Asosiy", "endpoint": "/api/v1/client/home/"},
                {"key": "orders", "label": "Buyurtmalar", "endpoint": "/api/v1/client/orders/"},
                {"key": "market", "label": "Market", "endpoint": "/api/v1/client/market/"},
                {"key": "profile", "label": "Profil", "endpoint": "/api/v1/client/profile/"},
            ],
            "websocket": {
                "notifications": "/ws/client/notifications/",
                "support": "/ws/client/support/",
                "tracking_template": "/ws/client/track/{order_id}/",
                "auth_header": "Authorization: Bearer {access_token}",
            },
        }
        return success_response(data)


@extend_schema(tags=["Master Profile"])
class MasterProfileView(EnvelopeMixin, generics.RetrieveUpdateAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterProfileSerializer

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Master App"], summary="Master app bootstrap")
class MasterAppBootstrapView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterProfileSerializer

    def get(self, request):
        from django.db.models import Avg, F, Sum

        from apps.notifications.models import Notification
        from apps.orders.models import Order, OrderStatus, PaymentType, Review
        from apps.orders.serializers import OrderSerializer
        from apps.wallet.models import MasterWallet, WithdrawRequest
        from apps.wallet.serializers import MasterWalletSerializer, WithdrawRequestSerializer
        from apps.warehouse.models import MasterInventory
        from apps.warehouse.serializers import MasterInventorySerializer

        today = timezone.localdate()
        wallet, _ = MasterWallet.objects.get_or_create(master=request.user)
        current_orders = Order.objects.filter(
            master=request.user, status__in=[OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]
        ).select_related("service", "client", "tracking")[:5]
        new_orders = Order.objects.filter(status=OrderStatus.NEW, master__isnull=True).select_related("service", "client")[:10]
        completed_today = Order.objects.filter(master=request.user, status=OrderStatus.COMPLETED, scheduled_date=today)
        data = {
            "profile": MasterProfileSerializer(request.user).data,
            "availability": {
                "is_online": request.user.is_online,
                "is_available": request.user.is_available,
                "lat": request.user.lat,
                "lng": request.user.lng,
                "last_location_at": request.user.last_location_at,
            },
            "stats": {
                "today_income": completed_today.aggregate(total=Sum("total_amount"))["total"] or 0,
                "today_orders": Order.objects.filter(master=request.user, scheduled_date=today).count(),
                "orders_count": Order.objects.filter(master=request.user).count(),
                "new_orders_count": Order.objects.filter(status=OrderStatus.NEW, master__isnull=True).count(),
                "in_process_orders_count": Order.objects.filter(
                    master=request.user, status__in=[OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]
                ).count(),
                "average_rating": Review.objects.filter(master=request.user).aggregate(avg=Avg("rating"))["avg"] or 0,
                "low_stock_count": MasterInventory.objects.filter(master=request.user, quantity__lte=F("low_threshold")).count(),
                "unread_notifications": Notification.objects.filter(master=request.user, is_read=False).count(),
            },
            "orders": {
                "new": OrderSerializer(new_orders, many=True, context={"request": request}).data,
                "current": OrderSerializer(current_orders, many=True, context={"request": request}).data,
            },
            "wallet": MasterWalletSerializer(wallet, context={"request": request}).data,
            "withdraw_requests": WithdrawRequestSerializer(
                WithdrawRequest.objects.filter(master=request.user)[:5],
                many=True,
                context={"request": request},
            ).data,
            "inventory": {
                "low_stock": MasterInventorySerializer(
                    MasterInventory.objects.filter(master=request.user, quantity__lte=F("low_threshold"))[:5],
                    many=True,
                    context={"request": request},
                ).data
            },
            "choices": {
                "languages": app_language_items(request.user.language),
                "order_statuses": [{"value": value, "label": label} for value, label in OrderStatus.choices],
                "payment_types": [{"value": value, "label": label} for value, label in PaymentType.choices],
            },
            "navigation": [
                {"key": "home", "label": "Asosiy", "endpoint": "/api/v1/master/home/stats/"},
                {"key": "orders", "label": "Buyurtmalar", "endpoint": "/api/v1/master/orders/"},
                {"key": "wallet", "label": "Hamyon", "endpoint": "/api/v1/master/wallet/"},
                {"key": "inventory", "label": "Ombor", "endpoint": "/api/v1/master/inventory/"},
                {"key": "profile", "label": "Profil", "endpoint": "/api/v1/master/profile/"},
            ],
            "websocket": {
                "tracking": "/ws/master/tracking/",
                "notifications": "/ws/master/notifications/",
                "support": "/ws/master/support/",
                "auth_header": "Authorization: Bearer {access_token}",
            },
        }
        return success_response(data)


@extend_schema(tags=["Master Profile"])
class MasterSettingsView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterProfileSerializer

    def patch(self, request):
        allowed = {"notifications_enabled", "push_enabled", "is_online", "is_available"}
        for field in allowed:
            if field in request.data:
                setattr(request.user, field, request.data[field])
        request.user.save(update_fields=list(allowed))
        return success_response(MasterProfileSerializer(request.user).data)


@extend_schema(
    tags=["Client Profile"],
    summary="Notification/push sozlamalarini o'zgartirish",
    description="Profile page'dagi `Bildirishnomalar` toggle uchun. `notifications_enabled` va `push_enabled` qabul qiladi.",
    examples=[
        OpenApiExample(
            "Notification settings request",
            value={"notifications_enabled": True, "push_enabled": True},
            request_only=True,
        )
    ],
)
class ClientNotificationSettingsView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientSerializer

    def patch(self, request):
        for field in ("notifications_enabled", "push_enabled"):
            if field in request.data:
                setattr(request.user, field, request.data[field])
        request.user.save(update_fields=["notifications_enabled", "push_enabled"])
        return success_response(ClientSerializer(request.user).data)


@extend_schema_view(post=extend_schema(tags=["Master Push"]))
class MasterPushRegisterView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = FCMDeviceSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device, created = FCMDevice.objects.update_or_create(
            token=serializer.validated_data["token"],
            defaults={
                "role": "master",
                "master": request.user,
                "client": None,
                "platform": serializer.validated_data.get("platform", ""),
                "is_active": True,
            },
        )
        request.user.fcm_token = device.token
        request.user.save(update_fields=["fcm_token"])
        return success_response(FCMDeviceSerializer(device).data, status=201 if created else 200)


@extend_schema_view(post=extend_schema(tags=["Client Push"]))
class ClientPushRegisterView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = FCMDeviceSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device, created = FCMDevice.objects.update_or_create(
            token=serializer.validated_data["token"],
            defaults={
                "role": "client",
                "client": request.user,
                "master": None,
                "platform": serializer.validated_data.get("platform", ""),
                "is_active": True,
            },
        )
        request.user.fcm_token = device.token
        request.user.save(update_fields=["fcm_token"])
        return success_response(FCMDeviceSerializer(device).data, status=201 if created else 200)
