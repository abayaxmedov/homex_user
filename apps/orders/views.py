from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db.models import Avg, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.accounts.models import Master
from apps.accounts.permissions import IsClient, IsMaster
from apps.accounts.serializers import MasterSummarySerializer
from apps.common.geo import distance_km, eta_minutes
from apps.common.responses import success_response
from apps.common.views import EnvelopeMixin
from apps.notifications.models import Notification
from apps.notifications.services import create_notification
from apps.orders.models import Order, OrderStatus, OrderTracking, Review
from apps.orders.serializers import (
    MasterLocationSerializer,
    MapConfigSerializer,
    NearbyMasterSerializer,
    OrderCancelSerializer,
    OrderCompleteSerializer,
    OrderRejectSerializer,
    OrderSerializer,
    PaymentStartSerializer,
    ReviewSerializer,
)
from apps.services.models import ServiceCategory
from apps.services.serializers import ServiceCategorySerializer
from apps.wallet.models import MasterWallet
from apps.warehouse.models import MasterInventory


def tracking_payload(order):
    tracking = getattr(order, "tracking", None)
    master = order.master
    master_lat = getattr(tracking, "master_lat", None) or getattr(master, "lat", None)
    master_lng = getattr(tracking, "master_lng", None) or getattr(master, "lng", None)
    calculated_distance = getattr(tracking, "distance_km", None)
    if calculated_distance is None and master_lat is not None and master_lng is not None:
        calculated_distance = distance_km(master_lat, master_lng, order.lat, order.lng)
    calculated_eta = getattr(tracking, "eta_minutes", None) or eta_minutes(calculated_distance)
    return {
        "order_id": order.id,
        "status": order.status,
        "order_location": {"lat": order.lat, "lng": order.lng, "address": order.address_text},
        "master": MasterSummarySerializer(master).data if master else None,
        "master_location": {
            "lat": master_lat,
            "lng": master_lng,
            "last_location_at": getattr(master, "last_location_at", None),
        },
        "distance_km": calculated_distance,
        "eta_minutes": calculated_eta,
        "websocket": {"client_track": f"/ws/client/track/{order.id}/", "master_tracking": "/ws/master/tracking/"},
    }


def broadcast_tracking(order, payload):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            f"order_tracking_{order.id}",
            {"type": "location.update", "payload": payload},
        )
    except Exception:
        return


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
            "new_orders_count": Order.objects.filter(status=OrderStatus.NEW, master__isnull=True).count(),
            "in_process_orders_count": Order.objects.filter(
                master=request.user, status__in=[OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS]
            ).count(),
            "average_rating": Review.objects.filter(master=request.user).aggregate(avg=Avg("rating"))["avg"] or 0,
            "wallet": {
                "balance_online": wallet.balance_online,
                "balance_cash": wallet.balance_cash,
                "total_earned": wallet.total_earned,
                "total_withdrawn": wallet.total_withdrawn,
            },
            "low_stock_count": MasterInventory.objects.filter(master=request.user, quantity__lte=F("low_threshold")).count(),
            "unread_notifications": Notification.objects.filter(master=request.user, is_read=False).count(),
            "websocket": {
                "tracking": "/ws/master/tracking/",
                "notifications": "/ws/master/notifications/",
                "support": "/ws/master/support/",
            },
        }
        return success_response(data)


@extend_schema_view(get=extend_schema(tags=["Master Orders"]))
class MasterOrderListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        tab = self.request.query_params.get("tab")
        queryset = Order.objects.select_related("service", "master", "client", "tracking")
        if tab in {"yangi", "new", "available"}:
            queryset = queryset.filter(Q(master=self.request.user) | Q(master__isnull=True), status=OrderStatus.NEW)
        elif tab in {"joriy", "in_process"}:
            queryset = queryset.filter(master=self.request.user, status__in=[OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS])
        elif tab in {"completed", "bajarilgan"}:
            queryset = queryset.filter(master=self.request.user, status=OrderStatus.COMPLETED)
        else:
            queryset = queryset.filter(master=self.request.user)
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
            Q(master=self.request.user) | Q(master__isnull=True, status=OrderStatus.NEW)
        ).select_related("service", "client", "master", "tracking")


@extend_schema(tags=["Master Orders"])
class MasterOrderAcceptView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, Q(master=request.user) | Q(master__isnull=True), pk=pk, status=OrderStatus.NEW)
        order.master = request.user
        order.status = OrderStatus.ACCEPTED
        order.save(update_fields=["master", "status", "updated_at"])
        create_notification(
            role="client",
            client=order.client,
            title="Buyurtma qabul qilindi",
            body=f"{request.user.full_name} buyurtmangizni qabul qildi",
            data={"order_id": str(order.id), "status": order.status},
        )
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
        create_notification(
            role="client",
            client=order.client,
            title="Buyurtma rad etildi",
            body=order.rejected_reason,
            data={"order_id": str(order.id), "status": order.status},
        )
        return success_response(OrderSerializer(order).data)


@extend_schema(tags=["Master Orders"])
class MasterOrderCompleteView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderCompleteSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, master=request.user)
        serializer = self.get_serializer(data=request.data, context={"order": order})
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        wallet = getattr(request.user, "wallet", None)
        create_notification(
            role="client",
            client=order.client,
            title="Buyurtma yakunlandi",
            body="Usta buyurtmani yakunladi",
            data={"order_id": str(order.id), "status": order.status, "total_amount": str(order.total_amount)},
        )
        return success_response(
            {
                "order": OrderSerializer(order).data,
                "service_fee": order.service_fee,
                "inventory_total": order.inventory_total,
                "total_amount": order.total_amount,
                "wallet_balance": getattr(wallet, "balance_cash", 0) + getattr(wallet, "balance_online", 0),
            }
        )


@extend_schema(tags=["Master Orders"])
class MasterOrderTrackView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def get(self, request, pk):
        order = get_object_or_404(
            Order.objects.select_related("master", "tracking", "client"), pk=pk, master=request.user
        )
        return success_response(tracking_payload(order))


@extend_schema(tags=["Master Tracking"])
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
            "websocket": {"tracking": "/ws/master/tracking/?token={access_token}"},
        }
        order_id = data.get("order_id")
        if order_id:
            order = get_object_or_404(Order, pk=order_id, master=request.user)
            master_distance = data.get("distance_km") or distance_km(data["lat"], data["lng"], order.lat, order.lng)
            master_eta = data.get("eta_minutes") or eta_minutes(master_distance)
            tracking, _ = OrderTracking.objects.update_or_create(
                order=order,
                defaults={
                    "master_lat": data["lat"],
                    "master_lng": data["lng"],
                    "distance_km": master_distance,
                    "eta_minutes": master_eta,
                    "raw_payload": {key: str(value) for key, value in request.data.items()},
                },
            )
            response["tracking"] = tracking_payload(order)
            broadcast_tracking(
                order,
                {
                    "order_id": str(order.id),
                    "lat": str(tracking.master_lat),
                    "lng": str(tracking.master_lng),
                    "distance_km": float(tracking.distance_km) if tracking.distance_km is not None else None,
                    "eta_minutes": tracking.eta_minutes,
                    "updated_at": tracking.updated_at.isoformat(),
                },
            )
        return success_response(response)

    patch = post


@extend_schema(tags=["Client Home"])
class ClientHomeView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get(self, request):
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
                "websocket": {
                    "notifications": "/ws/client/notifications/",
                    "support": "/ws/client/support/",
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
                "tracking_ws_template": "/ws/client/track/{order_id}/?token={access_token}",
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


@extend_schema_view(get=extend_schema(tags=["Client Masters"]))
class NearbyMasterListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsClient]
    serializer_class = NearbyMasterSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = Master.objects.filter(is_online=True, is_active=True, is_available=True)
        specialization = self.request.query_params.get("specialization")
        if specialization:
            queryset = queryset.filter(specialization__icontains=specialization)
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


@extend_schema_view(get=extend_schema(tags=["Client Orders"]), post=extend_schema(tags=["Client Orders"]))
class ClientOrderListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        queryset = Order.objects.filter(client=self.request.user).select_related("service", "master", "tracking")
        status = self.request.query_params.get("status")
        return queryset.filter(status=status) if status else queryset

    def perform_create(self, serializer):
        order = serializer.save(client=self.request.user)
        masters = Master.objects.filter(is_active=True, is_online=True, is_available=True)[:50]
        for master in masters:
            create_notification(
                role="master",
                master=master,
                title="Yangi buyurtma",
                body=order.address_text,
                data={"order_id": str(order.id), "status": order.status},
            )


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
        return success_response(OrderSerializer(order).data)


@extend_schema(tags=["Client Orders"])
class ClientOrderTrackView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get(self, request, pk):
        order = get_object_or_404(
            Order.objects.select_related("master", "tracking", "client"), pk=pk, client=request.user
        )
        return success_response(tracking_payload(order))


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
