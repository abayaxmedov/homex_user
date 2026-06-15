from django.db.models import Avg, Count, Sum
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.accounts.models import Master
from apps.accounts.permissions import IsClient, IsMaster
from apps.common.responses import success_response
from apps.common.views import EnvelopeMixin
from apps.orders.models import Order, OrderStatus, Review
from apps.orders.serializers import (
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


@extend_schema(tags=["Master Home"])
class MasterHomeStatsView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def get(self, request):
        completed = Order.objects.filter(master=request.user, status=OrderStatus.COMPLETED)
        data = {
            "today_income": completed.aggregate(total=Sum("total_amount"))["total"] or 0,
            "orders_count": Order.objects.filter(master=request.user).count(),
            "average_rating": Review.objects.filter(master=request.user).aggregate(avg=Avg("rating"))["avg"] or 0,
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
        queryset = Order.objects.filter(master=self.request.user).select_related("service", "master", "client")
        if tab == "yangi":
            queryset = queryset.filter(status=OrderStatus.NEW)
        elif tab == "joriy":
            queryset = queryset.filter(status__in=[OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS])
        date = self.request.query_params.get("date")
        return queryset.filter(scheduled_date=date) if date else queryset


@extend_schema_view(get=extend_schema(tags=["Master Orders"]))
class MasterOrderDetailView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return Order.objects.filter(master=self.request.user).select_related("service", "client", "master")


@extend_schema(tags=["Master Orders"])
class MasterOrderAcceptView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = OrderSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, master=request.user, status=OrderStatus.NEW)
        order.status = OrderStatus.ACCEPTED
        order.save(update_fields=["status", "updated_at"])
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
        order = get_object_or_404(Order, pk=pk, master=request.user)
        return success_response({"order_id": order.id, "lat": order.lat, "lng": order.lng, "address": order.address_text})


@extend_schema(tags=["Client Home"])
class ClientHomeView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get(self, request):
        categories = ServiceCategory.objects.filter(is_active=True).prefetch_related("services")
        active_orders = Order.objects.filter(client=request.user).exclude(
            status__in=[OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED]
        )[:5]
        return success_response(
            {
                "services": ServiceCategorySerializer(categories, many=True).data,
                "active_orders": OrderSerializer(active_orders, many=True).data,
                "nearby_masters": NearbyMasterSerializer(Master.objects.filter(is_online=True)[:10], many=True).data,
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
        return Master.objects.filter(is_online=True, is_active=True)


@extend_schema_view(get=extend_schema(tags=["Client Orders"]), post=extend_schema(tags=["Client Orders"]))
class ClientOrderListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        queryset = Order.objects.filter(client=self.request.user).select_related("service", "master")
        status = self.request.query_params.get("status")
        return queryset.filter(status=status) if status else queryset

    def perform_create(self, serializer):
        serializer.save(client=self.request.user)


@extend_schema_view(get=extend_schema(tags=["Client Orders"]))
class ClientOrderDetailView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Order.objects.none()
        return Order.objects.filter(client=self.request.user).select_related("service", "master")


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
        return success_response(OrderSerializer(order).data)


@extend_schema(tags=["Client Orders"])
class ClientOrderTrackView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = OrderSerializer

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk, client=request.user)
        return success_response({"order_id": order.id, "master": order.master_id, "lat": None, "lng": None})


@extend_schema(tags=["Client Orders"])
class ClientOrderRateView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = ReviewSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, client=request.user, status=OrderStatus.COMPLETED)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save(order=order, client=request.user, master=order.master)
        return success_response(ReviewSerializer(review).data, status=201)


@extend_schema(tags=["Client Orders"])
class ClientOrderPayView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = PaymentStartSerializer

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, client=request.user)
        serializer = self.get_serializer(data=request.data, context={"order": order})
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.save())


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
