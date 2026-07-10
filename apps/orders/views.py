from django.conf import settings
from django.db.models import Avg, F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny

from apps.accounts.models import Master
from apps.accounts.permissions import IsClient, IsMaster
from apps.accounts.serializers import MasterSummarySerializer
from apps.common.filters import filter_by_category
from apps.common.geo import distance_km, eta_minutes
from apps.common.responses import success_response
from apps.common.views import EnvelopeMixin
from apps.notifications.models import Notification
from apps.notifications.services import create_notification
from apps.orders.models import ACTIVE_ORDER_STATUSES, HomeBanner, Order, OrderMaster, OrderStatus, Review
from apps.orders.receipts import DOCX_CONTENT_TYPE, build_order_receipt_docx, order_receipt_filename
from apps.orders.serializers import (
    MasterLocationSerializer,
    MapConfigSerializer,
    NearbyMasterSerializer,
    OrderCancelSerializer,
    OrderCompleteSerializer,
    OrderRejectSerializer,
    OrderSerializer,
    OrderStartSerializer,
    PaymentStartSerializer,
    ReviewSerializer,
)
from apps.accounts.filters import filter_masters_by_specialization
from apps.orders.tracking import (
    broadcast_tracking,
    ensure_tracking,
    refresh_master_order_tracking,
    tracking_payload,
)
from apps.services.models import ServiceCategory
from apps.services.serializers import ServiceCategorySerializer
from apps.wallet.models import MasterWallet
from apps.warehouse.models import MasterInventory


ORDER_STATUS_TEXT = (
    "`new` - Usta qidirilmoqda (admin biriktiradi); `accepted` - usta qabul qildi; `on_way` - usta yo'lda; "
    "`arrived` - usta yetib keldi; `completed` - usta ishni tugatgan; `cancelled` - client bekor qilgan; "
    "`rejected` - master rad qilgan."
)

ORDER_CREATE_EXAMPLE = {
    "service": "service_uuid",
    "address": "address_uuid",
    "address_text": "Chilonzor, Tashkent",
    "lat": "41.30000000",
    "lng": "69.25000000",
    "scheduled_date": "2026-06-25",
    "scheduled_time": "10:00:00",
    "payment_type": "cash",
    "note": "Konditsioner ishlamayapti",
}

TRACKING_RESPONSE_EXAMPLE = {
    "success": True,
    "message": "OK",
    "data": {
        "order_id": "order_uuid",
        "status": "accepted",
        "tracking_status": "master_on_way",
        "tracking_status_label": "Usta yo'lda",
        "tracking_step": 2,
        "tracking_total_steps": 4,
        "before_photo": "/media/orders/before/photo.jpg",
        "completion_photo": None,
        "receipt_status": "not_ready",
        "receipt_available": False,
        "receipt_download_url": None,
        "order_location": {"lat": "41.30000000", "lng": "69.25000000", "address": "Chilonzor, Tashkent"},
        "master": {"id": "master_uuid", "full_name": "Ali Usta", "rating": "4.90"},
        "master_contact": {"phone_number": "+998901112233"},
        "master_location": {"lat": "41.30100000", "lng": "69.25100000", "last_location_at": "2026-06-25T10:00:00+05:00"},
        "distance_km": 1.2,
        "eta_minutes": 3,
        "websocket": {
            "client_track": "/ws/client/track/order_uuid/",
            "master_tracking": "/ws/master/tracking/",
            "auth_header": "Authorization: Bearer {access_token}",
        },
    },
}


DEFAULT_HOME_BANNERS = [
    {
        "id": "00000000-0000-0000-0000-000000000000",
        "banner_image": None,
        "banner_url": None,
        "is_active": True,
    }
]


def get_home_banners(request):
    banners = [banner.as_home_payload(request) for banner in HomeBanner.objects.filter(is_active=True).order_by("id")]
    return banners or DEFAULT_HOME_BANNERS


def receipt_download_url(request, order):
    url = reverse("client-order-receipt-download", args=[order.id])
    return request.build_absolute_uri(url) if request else url


def approve_order_receipt(order, master):
    if order.status != OrderStatus.COMPLETED:
        raise ValidationError({"status": "Check faqat completed order uchun tasdiqlanadi"})
    if order.receipt_approved_at:
        return False
    order.receipt_approved_at = timezone.now()
    order.receipt_approved_by = master
    order.save(update_fields=["receipt_approved_at", "receipt_approved_by", "updated_at"])
    return True


@extend_schema(tags=["Master Home"])
class MasterHomeStatsView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def get(self, request):
        today = timezone.localdate()
        completed = Order.objects.filter(master=request.user, status=OrderStatus.COMPLETED)
        completed_today = completed.filter(scheduled_date=today)
        wallet, _ = MasterWallet.objects.get_or_create(master=request.user)
        data = {
            "today_income": completed_today.aggregate(total=Sum("total_amount"))["total"] or 0,
            "today_orders": Order.objects.filter(master=request.user, scheduled_date=today).count(),
            "orders_count": Order.objects.filter(master=request.user).count(),
            "new_orders_count": Order.objects.filter(
                assigned_masters__master=request.user, status=OrderStatus.NEW
            ).distinct().count(),
            "in_process_orders_count": Order.objects.filter(
                assigned_masters__master=request.user, status__in=ACTIVE_ORDER_STATUSES
            ).distinct().count(),
            "average_rating": Review.objects.filter(master=request.user).aggregate(avg=Avg("rating"))["avg"] or 0,
            "wallet": {
                "balance_online": wallet.balance_online,
                "balance_cash": wallet.balance_cash,
                "total_balance": wallet.total_balance,
                "total_earned": wallet.total_earned,
                "total_withdrawn": wallet.total_withdrawn,
            },
            "low_stock_count": MasterInventory.objects.filter(master=request.user, quantity__lte=F("low_threshold")).count(),
            "unread_notifications": Notification.objects.filter(master=request.user, is_read=False).count(),
            "websocket": {
                "tracking": "/ws/master/tracking/",
                "notifications": "/ws/master/notifications/",
                "support": "/ws/master/support/",
                "auth_header": "Authorization: Bearer {access_token}",
            },
        }
        return success_response(data)


@extend_schema_view(
    get=extend_schema(
        tags=["Master Orders"],
        summary="Master order list",
        description=(
            "Master uchun orderlar ro'yxati. `tab=yangi` yangi/unassigned orderlarni, `tab=joriy` qabul qilingan "
            "yoki jarayondagi orderlarni, `tab=completed` bajarilgan orderlarni qaytaradi. "
            f"Order statuslari: {ORDER_STATUS_TEXT}"
        ),
        parameters=[
            OpenApiParameter(
                name="tab",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Qiymatlar: `yangi`, `new`, `available`, `joriy`, `in_process`, `completed`, `bajarilgan`.",
                required=False,
            ),
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Orderlarni scheduled_date bo'yicha filter qiladi. Format: `YYYY-MM-DD`.",
                required=False,
            ),
            OpenApiParameter(
                name="category",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Xizmat kategoriyasi bo'yicha filter (service kategoriyasi id yoki slug).",
                required=False,
            ),
        ],
    )
)
class MasterOrderListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        tab = self.request.query_params.get("tab")
        # Master only sees orders the admin assigned to them (dashboard "Usta biriktirish").
        queryset = (
            Order.objects.filter(assigned_masters__master=self.request.user, assigned_masters__is_active=True)
            .select_related("service", "service__category", "master", "client", "tracking")
            .distinct()
        )
        if tab in {"yangi", "new", "available"}:
            # Assigned but not yet accepted by anyone.
            queryset = queryset.filter(status=OrderStatus.NEW)
        elif tab in {"joriy", "in_process"}:
            queryset = queryset.filter(status__in=ACTIVE_ORDER_STATUSES)
        elif tab in {"completed", "bajarilgan"}:
            queryset = queryset.filter(status=OrderStatus.COMPLETED)
        queryset = filter_by_category(queryset, self.request, field="service__category")
        date = self.request.query_params.get("date")
        return queryset.filter(scheduled_date=date) if date else queryset


@extend_schema_view(get=extend_schema(tags=["Master Orders"]))
class MasterOrderDetailView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return Order.objects.filter(
            Q(assigned_masters__master=self.request.user) | Q(master=self.request.user)
        ).select_related("service", "client", "master", "tracking").distinct()


@extend_schema(
    tags=["Master Orders"],
    summary="Orderni qabul qilish",
    description=(
        "Admin biriktirgan usta orderni qabul qiladi. Birinchi qabul qilgan usta 'asosiy' (lead) bo'ladi va "
        "tracking shu usta uchun ishlaydi. Status `new` -> `accepted`."
    ),
)
class MasterOrderAcceptView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def post(self, request, pk):
        # Only a master the admin assigned to this order may accept it.
        assignment = get_object_or_404(
            OrderMaster.objects.select_related("order", "order__client"),
            order_id=pk,
            master=request.user,
            is_active=True,
        )
        order = assignment.order
        if order.status == OrderStatus.NEW:
            order.master = request.user  # first to accept becomes the lead master
            order.status = OrderStatus.ACCEPTED
            order.save(update_fields=["master", "status", "updated_at"])
            ensure_tracking(order)
            # The client status notification is fired centrally by the Order post_save signal.
        if not assignment.has_accepted:
            assignment.has_accepted = True
            assignment.save(update_fields=["has_accepted", "updated_at"])
        return success_response(OrderSerializer(order).data)


@extend_schema(
    tags=["Master Orders"],
    summary="Usta yo'lga chiqdi",
    description="Lead usta yo'lga chiqqanini bildiradi. Status `accepted` -> `on_way`. Client tracking socketiga yuboriladi.",
    request=None,
    responses=OrderSerializer,
)
class MasterOrderOnWayView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, master=request.user)
        if order.status != OrderStatus.ACCEPTED:
            raise ValidationError({"status": "Order faqat 'accepted' holatidan 'on_way' holatiga o'tadi"})
        order.status = OrderStatus.ON_WAY
        order.save(update_fields=["status", "updated_at"])
        ensure_tracking(order)
        # The client status notification is fired centrally by the Order post_save signal.
        return success_response(OrderSerializer(order).data)


@extend_schema(
    tags=["Master Orders"],
    summary="Usta yetib keldi",
    description=(
        "Lead usta manzilga yetib borgach order statusini `arrived` qiladi va client tracking socketiga yuboradi. "
        "Status `on_way` -> `arrived`. Multipart request bilan `before_photo` optional yuboriladi."
    ),
    request={"multipart/form-data": OrderStartSerializer},
    responses=OrderSerializer,
)
class MasterOrderStartView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderStartSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, master=request.user)
        serializer = self.get_serializer(data=request.data, context={"order": order})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        ensure_tracking(order)
        # The client status notification is fired centrally by the Order post_save signal.
        return success_response(OrderSerializer(order).data)


@extend_schema(tags=["Master Orders"])
class MasterOrderRejectView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderRejectSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, master=request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order.status = OrderStatus.REJECTED
        order.rejected_reason = serializer.validated_data["reason"]
        order.save(update_fields=["status", "rejected_reason", "updated_at"])
        # The client status notification is fired centrally by the Order post_save signal.
        return success_response(OrderSerializer(order).data)


@extend_schema(
    tags=["Master Orders"],
    summary="Orderni yakunlash",
    description=(
        "Master bajarilgan orderni yakunlaydi. Multipart request ishlatiladi: `completion_photo` optional. "
        "`used_items` inventory ishlatilgan bo'lsa JSON string/list sifatida yuboriladi. Yakunlanganda order total, "
        "wallet transaction va client notification yangilanadi."
    ),
    request={"multipart/form-data": OrderCompleteSerializer},
    examples=[
        OpenApiExample(
            "Complete order multipart fields",
            value={
                "service_fee": "285000.00",
                "payment_type": "cash",
                "used_items": [{"inventory_id": "inventory_uuid", "quantity": "1", "unit_price": "50000.00"}],
            },
            request_only=True,
        )
    ],
)
class MasterOrderCompleteView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderCompleteSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, master=request.user)
        serializer = self.get_serializer(data=request.data, context={"order": order})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        wallet = getattr(request.user, "wallet", None)
        # The client status notification is fired centrally by the Order post_save signal.
        return success_response(
            {
                "order": OrderSerializer(order, context={"request": request}).data,
                "service_fee": order.service_fee,
                "inventory_total": order.inventory_total,
                "total_amount": order.total_amount,
                "wallet_balance": getattr(wallet, "balance_cash", 0) + getattr(wallet, "balance_online", 0),
            }
        )


@extend_schema(
    tags=["Master Orders"],
    summary="Checkni tasdiqlash va clientga ochish",
    description="Order completed bo'lgandan keyin master checkni tasdiqlaydi. Shundan keyin client Word checkni yuklab oladi.",
    request=None,
    responses=OrderSerializer,
)
class MasterOrderReceiptConfirmView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, master=request.user)
        approved_now = approve_order_receipt(order, request.user)
        if approved_now:
            create_notification(
                role="client",
                client=order.client,
                title="Check tayyor",
                body="Usta checkni tasdiqladi. Endi Word faylni yuklab olishingiz mumkin.",
                data={
                    "order_id": str(order.id),
                    "status": order.status,
                    "receipt_available": True,
                    "receipt_download_url": receipt_download_url(request, order),
                },
            )
        return success_response(OrderSerializer(order, context={"request": request}).data)


@extend_schema(tags=["Master Orders"])
class MasterOrderTrackView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def get(self, request, pk):
        # The lead master OR any assigned master (even before accepting) can track.
        order = get_object_or_404(
            Order.objects.select_related("master", "tracking", "client").filter(
                Q(master=request.user)
                | Q(assigned_masters__master=request.user, assigned_masters__is_active=True)
            ).distinct(),
            pk=pk,
        )
        return success_response(tracking_payload(order))


@extend_schema(
    tags=["Master Tracking"],
    summary="Master location REST fallback",
    description=(
        "Master xaritada location yuboradi. Agar `order_id` berilsa, order tracking snapshot yangilanadi va "
        "client tracking WebSocket kanaliga event broadcast qilinadi. WebSocket token headerda yuboriladi."
    ),
    examples=[
        OpenApiExample(
            "Location update request",
            value={
                "lat": "41.30100000",
                "lng": "69.25100000",
                "is_online": True,
                "is_available": True,
                "order_id": "order_uuid",
            },
            request_only=True,
        )
    ],
)
class MasterLocationUpdateView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterLocationSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        request.user.lat = data["lat"]
        request.user.lng = data["lng"]
        request.user.is_online = data.get("is_online", True)
        request.user.is_available = data.get("is_available", True)
        request.user.last_location_at = timezone.now()
        request.user.save(update_fields=["lat", "lng", "is_online", "is_available", "last_location_at", "updated_at"])

        response = {
            "master": MasterSummarySerializer(request.user).data,
            "websocket": {
                "tracking": "/ws/master/tracking/",
                "auth_header": "Authorization: Bearer {access_token}",
            },
        }
        order_id = data.get("order_id")
        if order_id:
            # Keep the explicit-order contract: a foreign/unknown order is a 404.
            get_object_or_404(Order, pk=order_id, master=request.user)
        updates = refresh_master_order_tracking(
            request.user,
            data["lat"],
            data["lng"],
            order_id=order_id,
            distance_hint=data.get("distance_km"),
            eta_hint=data.get("eta_minutes"),
            raw_payload={key: str(value) for key, value in request.data.items()},
        )
        if order_id and updates:
            response["tracking"] = updates[0][1]
        for order, order_payload in updates:
            broadcast_tracking(order, order_payload, event_type="master.location")
        return success_response(response)

    patch = post


@extend_schema(tags=["Client Home"])
class ClientHomeView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = OrderSerializer

    def get_public_payload(self, request):
        categories = ServiceCategory.objects.filter(is_active=True).prefetch_related("services")
        return {
            "services": ServiceCategorySerializer(categories, many=True).data,
            "banners": get_home_banners(request),
        }

    def get(self, request):
        if not (request.user and getattr(request.user, "role", None) == "client"):
            return success_response(self.get_public_payload(request))

        categories = ServiceCategory.objects.filter(is_active=True).prefetch_related("services")
        active_orders = Order.objects.filter(client=request.user).exclude(
            status__in=[OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED]
        ).select_related("service", "master", "tracking")[:5]
        default_address = request.user.addresses.filter(is_default=True).first()
        unread_notifications = Notification.objects.filter(client=request.user, is_read=False).count()
        return success_response(
            {
                "services": ServiceCategorySerializer(categories, many=True).data,
                "active_orders": OrderSerializer(active_orders, many=True).data,
                "nearby_masters": NearbyMasterSerializer(Master.objects.filter(is_online=True)[:10], many=True).data,
                "default_address": {
                    "id": default_address.id,
                    "address_text": default_address.address_text,
                    "lat": default_address.lat,
                    "lng": default_address.lng,
                }
                if default_address
                else None,
                "counts": {
                    "active_orders": len(active_orders),
                    "unread_notifications": unread_notifications,
                    "devices": request.user.client_devices.count(),
                },
                "map": {
                    "provider": "google",
                    "api_key_configured": bool(settings.GOOGLE_MAPS_API_KEY),
                    "default_zoom": 14,
                },
                "quick_actions": [
                    {"key": "create_order", "label": "Buyurtma yaratish"},
                    {"key": "my_tools", "label": "Uskunalarim"},
                    {"key": "market", "label": "Market"},
                    {"key": "support", "label": "Qo'llab-quvvatlash"},
                ],
                "banners": get_home_banners(request),
                "websocket": {
                    "notifications": "/ws/client/notifications/",
                    "support": "/ws/client/support/",
                    "auth_header": "Authorization: Bearer {access_token}",
                },
            }
        )


@extend_schema(tags=["Client Home"])
class ClientMapConfigView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = MapConfigSerializer

    def get(self, request):
        return success_response(
            {
                "provider": "google",
                "google_maps_api_key": settings.GOOGLE_MAPS_API_KEY,
                "default_center": {"lat": 41.311081, "lng": 69.240562},
                "default_zoom": 14,
                "tracking_ws_template": "/ws/client/track/{order_id}/",
                "auth_header": "Authorization: Bearer {access_token}",
            }
        )


@extend_schema_view(get=extend_schema(tags=["Client Home"]))
class ClientRecentOrdersView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return Order.objects.filter(client=self.request.user).order_by("-created_at")[:5]


@extend_schema_view(
    get=extend_schema(
        tags=["Client Masters"],
        summary="Yaqin masterlar",
        description="Client map/home uchun yaqin online va available masterlarni qaytaradi. Distance va ETA hisoblanadi.",
        parameters=[
            OpenApiParameter("lat", OpenApiTypes.DECIMAL, OpenApiParameter.QUERY, description="Client latitude.", required=False),
            OpenApiParameter("lng", OpenApiTypes.DECIMAL, OpenApiParameter.QUERY, description="Client longitude.", required=False),
            OpenApiParameter("radius_km", OpenApiTypes.FLOAT, OpenApiParameter.QUERY, description="Qidiruv radiusi km. Default: 50.", required=False),
            OpenApiParameter("specialization", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Master specialization bo'yicha search.", required=False),
        ],
    )
)
class NearbyMasterListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsClient]
    serializer_class = NearbyMasterSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = Master.objects.filter(is_online=True, is_active=True, is_available=True)
        queryset = filter_masters_by_specialization(queryset, self.request.query_params.get("specialization"))
        lat = self.request.query_params.get("lat")
        lng = self.request.query_params.get("lng")
        try:
            radius = float(self.request.query_params.get("radius_km") or 50)
        except ValueError:
            radius = 50
        if not lat or not lng:
            return queryset
        masters = []
        for master in queryset:
            master_distance = distance_km(lat, lng, master.lat, master.lng)
            if master_distance is None or master_distance > radius:
                continue
            master.distance_km = master_distance
            master.eta_minutes = eta_minutes(master_distance)
            masters.append(master)
        return sorted(masters, key=lambda item: item.distance_km)


@extend_schema_view(
    get=extend_schema(
        tags=["Client Orders"],
        summary="Client order list",
        description=f"Client buyurtmalari. `status` query bilan filter qilish mumkin. Order statuslari: {ORDER_STATUS_TEXT}",
        parameters=[
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description="Qiymatlar: `new`, `accepted`, `on_way`, `arrived`, `completed`, `cancelled`, `rejected`.",
                required=False,
            ),
            OpenApiParameter(
                "category",
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description="Xizmat kategoriyasi bo'yicha filter (service kategoriyasi id yoki slug).",
                required=False,
            ),
        ],
    ),
    post=extend_schema(
        tags=["Client Orders"],
        summary="Yangi order yaratish",
        description=(
            "Client service, manzil, vaqt va payment type bilan yangi buyurtma yaratadi. Yaratilgandan keyin online/available "
            "masterlarga notification boradi. `payment_type`: `cash`, `online`, `card`, `plastic`."
        ),
        examples=[OpenApiExample("Create order request", value=ORDER_CREATE_EXAMPLE, request_only=True)],
    ),
)
class ClientOrderListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        queryset = Order.objects.filter(client=self.request.user).select_related(
            "service", "service__category", "master", "tracking"
        )
        queryset = filter_by_category(queryset, self.request, field="service__category")
        status = self.request.query_params.get("status")
        return queryset.filter(status=status) if status else queryset

    def perform_create(self, serializer):
        order = serializer.save(client=self.request.user)
        ensure_tracking(order)
        # No fan-out to online masters: this is an admin-assign model, so a new
        # order goes to nobody until an admin assigns it. The assign flow
        # (DashboardOrderAssignSerializer / admin) notifies ONLY the chosen
        # master(s) — a master's order info never reaches other masters.


@extend_schema_view(get=extend_schema(tags=["Client Orders"]))
class ClientOrderDetailView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return Order.objects.filter(client=self.request.user).select_related("service", "master", "tracking")


@extend_schema(tags=["Client Orders"])
class ClientOrderCancelView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderCancelSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, client=request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order.status = OrderStatus.CANCELLED
        order.cancel_reason = serializer.validated_data["reason"]
        order.save(update_fields=["status", "cancel_reason", "updated_at"])
        if order.master:
            create_notification(
                role="master",
                master=order.master,
                title="Buyurtma bekor qilindi",
                body=order.cancel_reason,
                data={"order_id": str(order.id), "status": order.status},
            )
        # Status broadcast is handled centrally by the Order post_save signal.
        return success_response(OrderSerializer(order).data)


@extend_schema(
    tags=["Client Orders"],
    summary="Client tracking snapshot",
    description=(
        "Client order tracking screen ochilganda avval shu REST endpointdan snapshot olinadi. Keyin response ichidagi "
        "`websocket.client_track` kanaliga ulaniladi. WebSocket auth header: `Authorization: Bearer <access_token>`."
    ),
    examples=[OpenApiExample("Tracking snapshot response", value=TRACKING_RESPONSE_EXAMPLE, response_only=True)],
)
class ClientOrderTrackView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get(self, request, pk):
        order = get_object_or_404(
            Order.objects.select_related("master", "tracking", "client"), pk=pk, client=request.user
        )
        return success_response(tracking_payload(order))


@extend_schema(
    tags=["Client Orders"],
    summary="Order check Word faylini yuklab olish",
    description="Client faqat usta checkni tasdiqlagandan keyin `.docx` checkni yuklab oladi.",
    responses={200: OpenApiTypes.BINARY},
)
class ClientOrderReceiptDownloadView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get(self, request, pk):
        order = get_object_or_404(
            Order.objects.select_related("client", "master", "service__category").prefetch_related(
                "inventory_usages__inventory__warehouse_product"
            ),
            pk=pk,
            client=request.user,
        )
        if order.status != OrderStatus.COMPLETED or not order.receipt_approved_at:
            raise PermissionDenied("Check hali usta tomonidan tasdiqlanmagan")

        content = build_order_receipt_docx(order, request=request)
        response = HttpResponse(content, content_type=DOCX_CONTENT_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{order_receipt_filename(order)}"'
        return response


@extend_schema(tags=["Client Orders"])
class ClientOrderRateView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = ReviewSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, client=request.user, status=OrderStatus.COMPLETED)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save(order=order, client=request.user, master=order.master)
        if order.master:
            create_notification(
                role="master",
                master=order.master,
                title="Yangi baho",
                body=f"{review.rating} yulduz",
                data={"order_id": str(order.id), "review_id": str(review.id), "rating": review.rating},
            )
        return success_response(ReviewSerializer(review).data, status=201)


@extend_schema(tags=["Client Orders"])
class ClientOrderPayView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = PaymentStartSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, client=request.user)
        serializer = self.get_serializer(data=request.data, context={"order": order})
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        if order.master:
            create_notification(
                role="master",
                master=order.master,
                title="To'lov boshlandi",
                body=f"Buyurtma uchun to'lov: {order.total_amount}",
                data={"order_id": str(order.id)},
            )
        return success_response(payment)


@extend_schema_view(get=extend_schema(tags=["Master Reviews"]))
class MasterReviewListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsMaster]
    serializer_class = ReviewSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Review.objects.none()
        queryset = Review.objects.filter(master=self.request.user)
        rating = self.request.query_params.get("rating")
        official = self.request.query_params.get("is_official")
        if rating:
            queryset = queryset.filter(rating=rating)
        if official is not None:
            queryset = queryset.filter(is_official=official.lower() == "true")
        return queryset


@extend_schema(tags=["Master Reviews"])
class MasterReviewSummaryView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = ReviewSerializer

    def get(self, request):
        reviews = Review.objects.filter(master=request.user)
        return success_response(
            {
                "rating": reviews.aggregate(avg=Avg("rating"))["avg"] or 0,
                "count": reviews.count(),
                "stars": {i: reviews.filter(rating=i).count() for i in range(1, 6)},
            }
        )
