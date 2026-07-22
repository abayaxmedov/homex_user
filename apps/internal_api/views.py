from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.filters import filter_masters_by_specialization
from apps.accounts.models import Client, Master
from apps.common.filters import filter_by_category
from apps.common.responses import success_response
from apps.orders.models import Order, OrderStatus
from apps.orders.receipts import PDF_CONTENT_TYPE, build_order_receipt_pdf, order_receipt_filename
from apps.profiles.models import Tariff
from apps.services.models import Service, ServiceCategory
from apps.wallet.models import MasterExpense
from .permissions import HasHomexServiceToken
from .serializers import (
    InternalClientSerializer,
    InternalClientWriteSerializer,
    InternalMasterSerializer,
    InternalMasterWriteSerializer,
    InternalOrderSerializer,
    InternalOrderWriteSerializer,
    InternalServiceCategorySerializer,
    InternalServiceCategoryWriteSerializer,
    InternalServiceSerializer,
    InternalServiceWriteSerializer,
    InternalTariffSerializer,
    InternalTariffWriteSerializer,
    apply_master_status,
    dashboard_order_status,
    master_status,
)


WEEKDAY_UZ = {
    0: "Dush",
    1: "Sesh",
    2: "Chor",
    3: "Pay",
    4: "Jum",
    5: "Shan",
    6: "Yak",
}

MONTH_UZ = {
    1: "Yan",
    2: "Fev",
    3: "Mart",
    4: "Apr",
    5: "May",
    6: "Iyun",
    7: "Iyul",
    8: "Avg",
    9: "Sen",
    10: "Okt",
    11: "Noy",
    12: "Dek",
}

ORDER_STATUS_COLORS = {
    "new": "#2563EB",
    "on_way": "#0891B2",
    "in_progress": "#F59E0B",
    "completed": "#16A34A",
    "cancelled": "#DC2626",
    "delayed": "#7C3AED",
}

MASTER_STATUS_COLORS = {
    "active": "#16A34A",
    "busy": "#F59E0B",
    "inactive": "#64748B",
    "blocked": "#DC2626",
}


class InternalPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "success": True,
                "data": {
                    "count": self.page.paginator.count,
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                    "results": data,
                },
                "message": "OK",
            }
        )


class InternalAPIViewMixin:
    authentication_classes = ()
    permission_classes = (HasHomexServiceToken,)
    pagination_class = InternalPagination
    read_serializer_class = None
    write_serializer_class = None

    def get_serializer_class(self):
        request = getattr(self, "request", None)
        if request and request.method in {"POST", "PUT", "PATCH"}:
            return self.write_serializer_class or self.serializer_class
        return self.read_serializer_class or self.serializer_class

    def serialize_instance(self, instance):
        serializer_class = self.read_serializer_class or self.serializer_class
        return serializer_class(instance, context=self.get_serializer_context()).data

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return success_response(self.serialize_instance(instance), status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        return success_response(self.serialize_instance(instance))

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return success_response({"deleted": True})


def money(value) -> int:
    return int(value or 0)


def format_uzs(value) -> str:
    return f"{money(value):,} so'm"


def percent_change(current, previous):
    current = Decimal(current or 0)
    previous = Decimal(previous or 0)
    if previous == 0:
        return (100 if current > 0 else 0), "up" if current > 0 else "flat"
    diff = ((current - previous) / previous) * 100
    direction = "up" if diff > 0 else "down" if diff < 0 else "flat"
    return int(abs(diff)), direction


def default_target_date():
    return timezone.localdate()


def parse_limit(request, default=10, maximum=100):
    try:
        return min(int(request.query_params.get("limit", default)), maximum)
    except (TypeError, ValueError):
        return default


def apply_search(queryset, request, fields):
    query = request.query_params.get("search") or request.query_params.get("q")
    if not query:
        return queryset
    condition = Q()
    for field in fields:
        condition |= Q(**{f"{field}__icontains": query})
    return queryset.filter(condition)


def get_stats(target_date):
    previous_date = target_date - timedelta(days=1)

    today_orders = Order.objects.filter(created_at__date=target_date).count()
    yesterday_orders = Order.objects.filter(created_at__date=previous_date).count()

    active_masters = Master.objects.filter(is_active=True, is_available=True).count()
    previous_active_masters = active_masters

    daily_income = (
        Order.objects.filter(status=OrderStatus.COMPLETED, updated_at__date=target_date).aggregate(total=Sum("total_amount"))[
            "total"
        ]
        or Decimal("0")
    )
    yesterday_income = (
        Order.objects.filter(status=OrderStatus.COMPLETED, updated_at__date=previous_date).aggregate(total=Sum("total_amount"))[
            "total"
        ]
        or Decimal("0")
    )

    daily_expense = MasterExpense.objects.filter(date=target_date).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    yesterday_expense = MasterExpense.objects.filter(date=previous_date).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    orders_change, orders_direction = percent_change(today_orders, yesterday_orders)
    masters_change, masters_direction = percent_change(active_masters, previous_active_masters)
    income_change, income_direction = percent_change(daily_income, yesterday_income)
    expense_change, expense_direction = percent_change(daily_expense, yesterday_expense)

    return {
        "today_orders": {
            "value": today_orders,
            "unit": "ta",
            "change_percent": orders_change,
            "change_direction": orders_direction,
        },
        "active_masters": {
            "value": active_masters,
            "unit": "ta",
            "change_percent": masters_change,
            "change_direction": masters_direction,
        },
        "daily_income": {
            "value": money(daily_income),
            "formatted": format_uzs(daily_income),
            "change_percent": income_change,
            "change_direction": income_direction,
        },
        "daily_expense": {
            "value": money(daily_expense),
            "formatted": format_uzs(daily_expense),
            "change_percent": expense_change,
            "change_direction": expense_direction,
        },
    }


def get_orders_by_service(date_from, date_to, limit=10):
    rows = (
        Order.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
        .values("service_id", "service__name")
        .annotate(orders_count=Count("id"))
        .order_by("-orders_count")[:limit]
    )
    items = list(rows)
    total = sum(item["orders_count"] for item in items)
    colors = ["#FF4E33", "#FF6B4A", "#FF9B45", "#FFC345", "#FFD98A"]
    return {
        "total": total,
        "items": [
            {
                "service_id": str(item["service_id"]),
                "service_name": item["service__name"],
                "orders_count": item["orders_count"],
                "percent": round((item["orders_count"] / total) * 100) if total else 0,
                "color": colors[index % len(colors)],
            }
            for index, item in enumerate(items)
        ],
    }


def get_weekly_orders(target_date):
    start_date = target_date - timedelta(days=6)
    rows = (
        Order.objects.filter(created_at__date__gte=start_date, created_at__date__lte=target_date)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            total=Count("id"),
            new=Count("id", filter=Q(status=OrderStatus.NEW)),
            on_way=Count("id", filter=Q(status=OrderStatus.ON_WAY)),
            in_progress=Count("id", filter=Q(status__in=[OrderStatus.ACCEPTED, OrderStatus.ARRIVED])),
            completed=Count("id", filter=Q(status=OrderStatus.COMPLETED)),
            cancelled=Count("id", filter=Q(status__in=[OrderStatus.CANCELLED, OrderStatus.REJECTED])),
        )
    )
    by_day = {row["day"]: row for row in rows}
    items = []
    for offset in range(7):
        day = start_date + timedelta(days=offset)
        row = by_day.get(day, {})
        items.append(
            {
                "date": day.isoformat(),
                "weekday": WEEKDAY_UZ[day.weekday()],
                "total": row.get("total", 0),
                "new": row.get("new", 0),
                "on_way": row.get("on_way", 0),
                "in_progress": row.get("in_progress", 0),
                "completed": row.get("completed", 0),
                "cancelled": row.get("cancelled", 0),
            }
        )
    return {"from": start_date.isoformat(), "to": target_date.isoformat(), "items": items}


def get_income_dynamics(target_date):
    start_date = target_date - timedelta(days=6)
    rows = (
        Order.objects.filter(
            status=OrderStatus.COMPLETED,
            updated_at__date__gte=start_date,
            updated_at__date__lte=target_date,
        )
        .annotate(day=TruncDate("updated_at"))
        .values("day")
        .annotate(income=Sum("total_amount"))
    )
    by_day = {row["day"]: row["income"] or Decimal("0") for row in rows}
    return {
        "unit": "million_uzs",
        "items": [
            {
                "date": (start_date + timedelta(days=offset)).isoformat(),
                "label": WEEKDAY_UZ[(start_date + timedelta(days=offset)).weekday()],
                "income": round(float(by_day.get(start_date + timedelta(days=offset), 0)) / 1_000_000, 2),
            }
            for offset in range(7)
        ],
    }


def get_income_expense(year):
    income_rows = (
        Order.objects.filter(status=OrderStatus.COMPLETED, updated_at__year=year)
        .annotate(month=TruncMonth("updated_at"))
        .values("month")
        .annotate(income=Sum("total_amount"))
    )
    expense_rows = (
        MasterExpense.objects.filter(date__year=year)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(expense=Sum("amount"))
    )
    income_by_month = {row["month"].month: row["income"] or Decimal("0") for row in income_rows}
    expense_by_month = {row["month"].month: row["expense"] or Decimal("0") for row in expense_rows}
    return {
        "unit": "million_uzs",
        "items": [
            {
                "month": month,
                "label": MONTH_UZ[month],
                "income": round(float(income_by_month.get(month, 0)) / 1_000_000, 2),
                "expense": round(float(expense_by_month.get(month, 0)) / 1_000_000, 2),
            }
            for month in range(1, 13)
        ],
    }


class DashboardMetaAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        today = timezone.localdate()
        return success_response(
            {
                "date": today.isoformat(),
                "weekday": WEEKDAY_UZ[today.weekday()],
                "timezone": str(timezone.get_current_timezone()),
                "languages": [
                    {"code": "ru", "label": "Russkiy", "is_active": False},
                    {"code": "uz", "label": "O'zbekcha", "is_active": True},
                    {"code": "en", "label": "English", "is_active": False},
                ],
            }
        )


class DashboardStatsAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        target_date = request.query_params.get("date")
        target_date = timezone.datetime.fromisoformat(target_date).date() if target_date else default_target_date()
        return success_response(get_stats(target_date))


class DashboardOrdersByServiceAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        date_to = request.query_params.get("date_to")
        date_from = request.query_params.get("date_from")
        date_to = timezone.datetime.fromisoformat(date_to).date() if date_to else default_target_date()
        date_from = timezone.datetime.fromisoformat(date_from).date() if date_from else date_to - timedelta(days=6)
        return success_response(get_orders_by_service(date_from, date_to, parse_limit(request)))


class DashboardWeeklyOrdersAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        target_date = request.query_params.get("date")
        target_date = timezone.datetime.fromisoformat(target_date).date() if target_date else default_target_date()
        return success_response(get_weekly_orders(target_date))


class DashboardIncomeDynamicsAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        target_date = request.query_params.get("date")
        target_date = timezone.datetime.fromisoformat(target_date).date() if target_date else default_target_date()
        return success_response(get_income_dynamics(target_date))


class DashboardIncomeExpenseAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        year = int(request.query_params.get("year", timezone.localdate().year))
        return success_response(get_income_expense(year))


class DashboardTodayOrdersAPIView(InternalAPIViewMixin, generics.ListAPIView):
    serializer_class = InternalOrderSerializer

    def get_queryset(self):
        target_date = default_target_date()
        return (
            Order.objects.select_related("client", "master", "service")
            .filter(
                created_at__date=target_date,
                status__in=[OrderStatus.NEW, OrderStatus.ACCEPTED, OrderStatus.ON_WAY, OrderStatus.ARRIVED],
            )
            .order_by("-created_at")
        )


class DashboardOverviewAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        target_date = request.query_params.get("date")
        target_date = timezone.datetime.fromisoformat(target_date).date() if target_date else default_target_date()
        orders_limit = parse_limit(request, default=8)
        date_from = target_date - timedelta(days=6)
        today_orders = (
            Order.objects.select_related("client", "master", "service")
            .filter(created_at__date=target_date, status__in=[OrderStatus.NEW, OrderStatus.ACCEPTED, OrderStatus.ON_WAY, OrderStatus.ARRIVED])
            .order_by("-created_at")[:orders_limit]
        )
        data = {
            "meta": {
                "date": target_date.isoformat(),
                "weekday": WEEKDAY_UZ[target_date.weekday()],
                "timezone": str(timezone.get_current_timezone()),
                "currency": "UZS",
            },
            "user": None,
            "stats": get_stats(target_date),
            "orders_by_service": get_orders_by_service(date_from, target_date)["items"],
            "weekly_orders": get_weekly_orders(target_date)["items"],
            "income_dynamics": get_income_dynamics(target_date)["items"],
            "income_expense": get_income_expense(target_date.year)["items"][:7],
            "today_orders": {
                "count": len(today_orders),
                "results": InternalOrderSerializer(today_orders, many=True, context={"request": request}).data,
            },
            "notifications": {"unread_count": 0},
        }
        return success_response(data)


class DashboardSearchAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return success_response({"query": query, "results": []})

        results = []
        for service in Service.objects.filter(name__icontains=query, is_active=True)[:5]:
            results.append({"type": "service", "id": str(service.id), "title": service.name, "subtitle": "Xizmat", "url": f"/services/{service.id}"})
        matching_orders = [
            order
            for order in Order.objects.select_related("client", "service").order_by("-created_at")[:50]
            if query.lower() in str(order.id).lower()
        ][:5]
        for order in matching_orders:
            results.append(
                {
                    "type": "order",
                    "id": str(order.id),
                    "title": f"HX{str(order.id).split('-')[0].upper()}",
                    "subtitle": f"{order.client} - {order.service.name}",
                    "url": f"/orders/{order.id}",
                }
            )
        for client in Client.objects.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(phone__icontains=query))[:5]:
            results.append({"type": "client", "id": str(client.id), "title": str(client), "subtitle": client.phone, "url": f"/clients/{client.id}"})
        for master in Master.objects.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(phone__icontains=query))[:5]:
            results.append({"type": "master", "id": str(master.id), "title": str(master), "subtitle": master.phone, "url": f"/masters/{master.id}"})
        return success_response({"query": query, "results": results[:10]})


class ClientCollectionAPIView(InternalAPIViewMixin, generics.ListCreateAPIView):
    read_serializer_class = InternalClientSerializer
    write_serializer_class = InternalClientWriteSerializer

    def get_queryset(self):
        queryset = Client.objects.select_related("current_tariff").prefetch_related("addresses", "orders").all()
        queryset = apply_search(queryset, self.request, ("first_name", "last_name", "phone"))
        if self.request.query_params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=self.request.query_params["is_active"] == "true")
        return queryset.order_by("first_name", "last_name")


class ClientDetailAPIView(InternalAPIViewMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Client.objects.select_related("current_tariff").prefetch_related("addresses", "orders").all()
    read_serializer_class = InternalClientSerializer
    write_serializer_class = InternalClientWriteSerializer


class ClientOrdersAPIView(InternalAPIViewMixin, generics.ListAPIView):
    serializer_class = InternalOrderSerializer

    def get_queryset(self):
        queryset = (
            Order.objects.select_related("client", "master", "service", "service__category")
            .filter(client_id=self.kwargs["pk"])
            .order_by("-created_at")
        )
        return filter_by_category(queryset, self.request, field="service__category")


class ClientStatsAPIView(InternalAPIViewMixin, APIView):
    def get(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        stats = Order.objects.filter(client=client).aggregate(total_orders=Count("id"), total_spent=Sum("total_amount"))
        last_order = client.orders.order_by("-created_at").first()
        return success_response(
            {
                "client_id": str(client.id),
                "total_orders": stats["total_orders"] or 0,
                "total_spent": stats["total_spent"] or 0,
                "last_order_date": last_order.created_at.date() if last_order else None,
            }
        )


class ClientSummaryAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        clients = Client.objects.all()
        totals = clients.aggregate(total_spent=Sum("total_spent"), total_orders=Sum("total_orders"))
        return success_response(
            {
                "total_clients": clients.count(),
                "active_clients": clients.filter(is_active=True).count(),
                "new_clients": clients.filter(total_orders=0).count(),
                "total_spent": totals["total_spent"] or 0,
                "total_orders": totals["total_orders"] or 0,
            }
        )


class MasterCollectionAPIView(InternalAPIViewMixin, generics.ListCreateAPIView):
    read_serializer_class = InternalMasterSerializer
    write_serializer_class = InternalMasterWriteSerializer

    def get_queryset(self):
        queryset = Master.objects.all()
        queryset = apply_search(queryset, self.request, ("first_name", "last_name", "phone", "specialization"))
        queryset = filter_masters_by_specialization(queryset, self.request.query_params.get("specialization"))
        status_value = self.request.query_params.get("status")
        if status_value in MASTER_STATUS_COLORS:
            queryset = [master for master in queryset if master_status(master) == status_value]
            return sorted(queryset, key=lambda item: (item.first_name, item.last_name, item.phone))
        return queryset.order_by("first_name", "last_name", "phone")


class MasterDetailAPIView(InternalAPIViewMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Master.objects.all()
    read_serializer_class = InternalMasterSerializer
    write_serializer_class = InternalMasterWriteSerializer


class AvailableMastersAPIView(MasterCollectionAPIView):
    def get_queryset(self):
        return Master.objects.filter(is_active=True, is_available=True).order_by("first_name", "last_name", "phone")


class AssistantCollectionAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        return success_response({"count": 0, "next": None, "previous": None, "results": []})

    def post(self, request):
        return success_response({"detail": "Assistant modeli homex_userda alohida mavjud emas."}, status=400)


class AssistantDetailAPIView(AssistantCollectionAPIView):
    def get(self, request, pk):
        return success_response(None, status=404)

    def put(self, request, pk):
        return success_response({"detail": "Assistant modeli homex_userda alohida mavjud emas."}, status=400)

    def patch(self, request, pk):
        return success_response({"detail": "Assistant modeli homex_userda alohida mavjud emas."}, status=400)

    def delete(self, request, pk):
        return success_response({"deleted": False})


class MasterMetaAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        masters = list(Master.objects.all())
        services = Service.objects.filter(is_active=True).order_by("name")
        status_counts = {key: 0 for key in MASTER_STATUS_COLORS}
        for master in masters:
            status_counts[master_status(master)] += 1
        return success_response(
            {
                "tabs": [
                    {"key": "all", "label": "Barchasi", "count": len(masters)},
                    *[
                        {"key": key, "label": label, "count": status_counts.get(key, 0), "color": MASTER_STATUS_COLORS[key]}
                        for key, label in (
                            ("active", "Faol"),
                            ("busy", "Band"),
                            ("inactive", "Dam olayapti"),
                            ("blocked", "Bloklangan"),
                        )
                    ],
                ],
                "statuses": [
                    {"value": "active", "label": "Faol", "color": MASTER_STATUS_COLORS["active"]},
                    {"value": "busy", "label": "Band", "color": MASTER_STATUS_COLORS["busy"]},
                    {"value": "inactive", "label": "Dam olayapti", "color": MASTER_STATUS_COLORS["inactive"]},
                    {"value": "blocked", "label": "Bloklangan", "color": MASTER_STATUS_COLORS["blocked"]},
                ],
                "degrees": [{"value": "master", "label": "Usta"}],
                "worker_types": [{"value": "master", "label": "Usta"}],
                "assistants_count": 0,
                "role_suggestions": [
                    {"value": f"{service.name} ustasi", "label": f"{service.name} ustasi", "service_id": str(service.id)}
                    for service in services
                ],
                "skills": [{"id": str(service.id), "name": service.name, "base_price": service.base_price} for service in services],
                "views": [{"value": "table", "label": "Jadval"}, {"value": "card", "label": "Kartochka"}],
            }
        )


class MasterStatsAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        masters = list(Master.objects.all())
        status_counts = {key: 0 for key in MASTER_STATUS_COLORS}
        for master in masters:
            status_counts[master_status(master)] += 1
        totals = Order.objects.aggregate(total_orders=Count("id"), total_income=Sum("total_amount"))
        return success_response(
            {
                "total_masters": len(masters),
                "active_masters": status_counts["active"],
                "busy_masters": status_counts["busy"],
                "inactive_masters": status_counts["inactive"],
                "blocked_masters": status_counts["blocked"],
                "verified_masters": len(masters),
                "total_orders": totals["total_orders"] or 0,
                "total_income": totals["total_income"] or 0,
                "statuses": [
                    {"value": key, "label": key, "color": color} for key, color in MASTER_STATUS_COLORS.items()
                ],
            }
        )


class MasterLocationAPIView(InternalAPIViewMixin, APIView):
    def get(self, request, pk):
        master = get_object_or_404(Master, pk=pk)
        return success_response(
            {
                "master_id": str(master.id),
                "full_name": str(master),
                "latitude": master.lat,
                "longitude": master.lng,
                "status": master_status(master),
                "last_location_at": master.last_location_at,
            }
        )


class MasterStatusAPIView(InternalAPIViewMixin, APIView):
    def patch(self, request, pk):
        master = get_object_or_404(Master, pk=pk)
        status_value = request.data.get("status")
        if status_value not in MASTER_STATUS_COLORS:
            return Response({"success": False, "message": "Status noto'g'ri", "details": {"status": status_value}}, status=400)
        apply_master_status(master, status_value)
        master.save()
        return success_response(InternalMasterSerializer(master, context={"request": request}).data, message="Usta statusi yangilandi")


class MasterBlockAPIView(InternalAPIViewMixin, APIView):
    def patch(self, request, pk):
        master = get_object_or_404(Master, pk=pk)
        is_blocked = bool(request.data.get("is_blocked"))
        apply_master_status(master, "blocked" if is_blocked else "active")
        master.save()
        return success_response(
            InternalMasterSerializer(master, context={"request": request}).data,
            message="Usta bloklandi" if is_blocked else "Usta blokdan chiqarildi",
        )


class MasterVerifyAPIView(InternalAPIViewMixin, APIView):
    def post(self, request, pk):
        master = get_object_or_404(Master, pk=pk)
        return success_response(InternalMasterSerializer(master, context={"request": request}).data, message="Usta verified holati yangilandi")


class MasterOrdersAPIView(InternalAPIViewMixin, generics.ListAPIView):
    serializer_class = InternalOrderSerializer

    def get_queryset(self):
        queryset = (
            Order.objects.select_related("client", "master", "service", "service__category")
            .filter(master_id=self.kwargs["pk"])
            .order_by("-created_at")
        )
        return filter_by_category(queryset, self.request, field="service__category")


class MasterScheduleAPIView(MasterOrdersAPIView):
    def get_queryset(self):
        queryset = (
            Order.objects.select_related("client", "master", "service", "service__category")
            .filter(master_id=self.kwargs["pk"])
            .exclude(status__in=[OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED])
            .order_by("scheduled_date", "scheduled_time", "created_at")
        )
        return filter_by_category(queryset, self.request, field="service__category")


class MasterIncomeAPIView(InternalAPIViewMixin, APIView):
    def get(self, request, pk):
        master = get_object_or_404(Master, pk=pk)
        stats = Order.objects.filter(master=master, status=OrderStatus.COMPLETED).aggregate(
            total_orders=Count("id"), total_income=Sum("total_amount")
        )
        return success_response(
            {
                "master_id": str(master.id),
                "total_orders": stats["total_orders"] or 0,
                "total_income": stats["total_income"] or 0,
                "rating": master.rating,
            }
        )


class MasterAssistantCollectionAPIView(InternalAPIViewMixin, APIView):
    def get(self, request, pk):
        return success_response([])

    def post(self, request, pk):
        return success_response({"detail": "Assistant relation homex_userda mavjud emas."}, status=400)


class MasterAssistantDetachAPIView(InternalAPIViewMixin, APIView):
    def delete(self, request, pk, assistant_id):
        return success_response({"deleted": 0}, message="Shogird buyurtmadan ajratildi")


class ServiceCategoryCollectionAPIView(InternalAPIViewMixin, generics.ListCreateAPIView):
    read_serializer_class = InternalServiceCategorySerializer
    write_serializer_class = InternalServiceCategoryWriteSerializer

    def get_queryset(self):
        queryset = ServiceCategory.objects.annotate(services_count=Count("services"))
        queryset = apply_search(queryset, self.request, ("name", "slug"))
        if self.request.query_params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=self.request.query_params["is_active"] == "true")
        return queryset.order_by("sort_order", "name")


class ServiceCategoryDetailAPIView(InternalAPIViewMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = ServiceCategory.objects.annotate(services_count=Count("services"))
    read_serializer_class = InternalServiceCategorySerializer
    write_serializer_class = InternalServiceCategoryWriteSerializer


class ServiceCategoryToggleAPIView(InternalAPIViewMixin, APIView):
    def patch(self, request, pk):
        category = get_object_or_404(ServiceCategory, pk=pk)
        category.is_active = bool(request.data.get("is_active"))
        category.save(update_fields=("is_active", "updated_at"))
        return success_response(InternalServiceCategorySerializer(category, context={"request": request}).data, message="Kategoriya holati yangilandi")


class CategoryServicesAPIView(InternalAPIViewMixin, generics.ListAPIView):
    serializer_class = InternalServiceSerializer

    def get_queryset(self):
        return Service.objects.select_related("category").filter(category_id=self.kwargs["pk"]).order_by("name")


class ServiceCollectionAPIView(InternalAPIViewMixin, generics.ListCreateAPIView):
    read_serializer_class = InternalServiceSerializer
    write_serializer_class = InternalServiceWriteSerializer

    def get_queryset(self):
        queryset = Service.objects.select_related("category").all()
        queryset = apply_search(queryset, self.request, ("name", "description", "category__name"))
        if self.request.query_params.get("category") or self.request.query_params.get("category_id"):
            queryset = queryset.filter(category_id=self.request.query_params.get("category") or self.request.query_params.get("category_id"))
        if self.request.query_params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=self.request.query_params["is_active"] == "true")
        return queryset.order_by("category__sort_order", "name")


class ServiceDetailAPIView(InternalAPIViewMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Service.objects.select_related("category").all()
    read_serializer_class = InternalServiceSerializer
    write_serializer_class = InternalServiceWriteSerializer


class ServiceMetaAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        categories = ServiceCategory.objects.annotate(services_count=Count("services")).order_by("sort_order", "name")
        services = Service.objects.all()
        return success_response(
            {
                "categories": InternalServiceCategorySerializer(categories, many=True, context={"request": request}).data,
                "statuses": [
                    {"value": "active", "label": "Faol", "count": services.filter(is_active=True).count()},
                    {"value": "inactive", "label": "O'chirilgan", "count": services.filter(is_active=False).count()},
                ],
                "tabs": [
                    {"key": "all", "label": "Barchasi", "count": services.count()},
                    {"key": "active", "label": "Faol", "count": services.filter(is_active=True).count()},
                    {"key": "inactive", "label": "O'chirilgan", "count": services.filter(is_active=False).count()},
                ],
            }
        )


class TariffCollectionAPIView(InternalAPIViewMixin, generics.ListCreateAPIView):
    read_serializer_class = InternalTariffSerializer
    write_serializer_class = InternalTariffWriteSerializer

    def get_queryset(self):
        queryset = Tariff.objects.prefetch_related("features").all()
        if self.request.query_params.get("is_active") in {"true", "false"}:
            queryset = queryset.filter(is_active=self.request.query_params["is_active"] == "true")
        period = self.request.query_params.get("period")
        if period == "monthly":
            queryset = queryset.filter(duration_days__lt=365)
        if period == "yearly":
            queryset = queryset.filter(duration_days__gte=365)
        return queryset.order_by("sort_order", "price", "name")


class TariffDetailAPIView(InternalAPIViewMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Tariff.objects.prefetch_related("features").all()
    read_serializer_class = InternalTariffSerializer
    write_serializer_class = InternalTariffWriteSerializer


class CurrentTariffAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        tariff = Tariff.objects.filter(is_active=True).order_by("sort_order", "price").first()
        data = InternalTariffSerializer(tariff, context={"request": request}).data if tariff else None
        return success_response(data)


class SubscribeTariffAPIView(InternalAPIViewMixin, APIView):
    def post(self, request):
        tariff = get_object_or_404(Tariff, pk=request.data.get("tariff") or request.data.get("tariff_id"))
        return success_response({"tariff": InternalTariffSerializer(tariff, context={"request": request}).data}, message="Tarif tanlandi")


class TariffMetaAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        tariffs = Tariff.objects.all()
        return success_response(
            {
                "periods": [
                    {"value": "monthly", "label": "Oylik", "count": tariffs.filter(duration_days__lt=365).count()},
                    {"value": "yearly", "label": "Yillik", "count": tariffs.filter(duration_days__gte=365).count()},
                ],
                "statuses": [
                    {"value": "active", "label": "Faol", "count": tariffs.filter(is_active=True).count()},
                    {"value": "inactive", "label": "O'chirilgan", "count": tariffs.filter(is_active=False).count()},
                ],
                "feature_flags": [
                    {"key": "has_analytics", "label": "Analitika"},
                    {"key": "has_priority_support", "label": "Priority support"},
                ],
                "limit_fields": [
                    {"key": "max_orders", "label": "Buyurtmalar limiti"},
                    {"key": "max_masters", "label": "Ustalar limiti"},
                ],
            }
        )


class OrderCollectionAPIView(InternalAPIViewMixin, generics.ListCreateAPIView):
    read_serializer_class = InternalOrderSerializer
    write_serializer_class = InternalOrderWriteSerializer

    def get_queryset(self):
        queryset = Order.objects.select_related("client", "master", "service", "service__category").all()
        params = self.request.query_params
        if params.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=params["date_to"])
        if params.get("master_id"):
            queryset = queryset.filter(master_id=params["master_id"])
        if params.get("client_id"):
            queryset = queryset.filter(client_id=params["client_id"])
        if params.get("service_id"):
            queryset = queryset.filter(service_id=params["service_id"])
        # Applied before the status branch below, which materialises the queryset into a list.
        queryset = filter_by_category(queryset, self.request, field="service__category")
        if params.get("status"):
            wanted = params["status"]
            queryset = [order for order in queryset if dashboard_order_status(order) == wanted]
            return sorted(queryset, key=lambda item: item.created_at, reverse=True)
        return queryset.order_by("-created_at")


class OrderDetailAPIView(InternalAPIViewMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Order.objects.select_related("client", "master", "service").all()
    read_serializer_class = InternalOrderSerializer
    write_serializer_class = InternalOrderWriteSerializer


class OrderStatusAPIView(InternalAPIViewMixin, APIView):
    def patch(self, request, pk):
        order = get_object_or_404(Order.objects.select_related("client", "master", "service"), pk=pk)
        serializer = InternalOrderWriteSerializer(order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return success_response(InternalOrderSerializer(order, context={"request": request}).data, message="Buyurtma statusi yangilandi")


class OrderReceiptDownloadAPIView(InternalAPIViewMixin, APIView):
    def get(self, request, pk):
        order = get_object_or_404(
            Order.objects.select_related("client", "master", "service__category").prefetch_related(
                "inventory_usages__inventory__warehouse_product"
            ),
            pk=pk,
        )
        if order.status not in (OrderStatus.AWAITING_PAYMENT, OrderStatus.COMPLETED) or not order.receipt_approved_at:
            raise PermissionDenied("Check hali usta tomonidan yuborilmagan")

        response = HttpResponse(build_order_receipt_pdf(order, request=request), content_type=PDF_CONTENT_TYPE)
        response["Content-Disposition"] = f'attachment; filename="{order_receipt_filename(order)}"'
        return response


class OrderAssignAPIView(InternalAPIViewMixin, APIView):
    def patch(self, request, pk):
        order = get_object_or_404(Order.objects.select_related("client", "master", "service"), pk=pk)
        master = None
        if request.data.get("master_id"):
            master = get_object_or_404(Master, pk=request.data["master_id"], is_active=True)
        order.master = master
        if master and order.status == OrderStatus.NEW:
            order.status = OrderStatus.ACCEPTED
        order.save(update_fields=("master", "status", "updated_at"))
        return success_response(InternalOrderSerializer(order, context={"request": request}).data, message="Usta tayinlandi")


class OrderAssignmentOptionsAPIView(InternalAPIViewMixin, APIView):
    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        masters = Master.objects.filter(is_active=True)
        selected_master_ids = {order.master_id} if order.master_id else set()
        items = []
        for master in masters:
            current_status = master_status(master)
            items.append(
                {
                    "id": master.id,
                    "first_name": master.first_name,
                    "last_name": master.last_name,
                    "full_name": str(master),
                    "phone": master.phone,
                    "role": master.specialization,
                    "avatar": master.avatar.url if master.avatar else None,
                    "worker_type": "master",
                    "status": current_status,
                    "status_label": current_status,
                    "availability_status": "available" if current_status == "active" else current_status,
                    "availability_label": "Bo'sh" if current_status == "active" else current_status,
                    "service_match": True,
                    "selected": master.id in selected_master_ids,
                }
            )
        return success_response({"order_id": order.id, "service_id": order.service_id, "masters": items, "assistants": []})


class OrderAssistantCollectionAPIView(InternalAPIViewMixin, APIView):
    def get(self, request, pk):
        return success_response([])

    def post(self, request, pk):
        return success_response({"detail": "Assistant modeli homex_userda alohida mavjud emas."}, status=400)

    def patch(self, request, pk):
        return success_response({"detail": "Assistant modeli homex_userda alohida mavjud emas."}, status=400)


class OrderAssistantDetachAPIView(InternalAPIViewMixin, APIView):
    def delete(self, request, pk, assistant_id):
        return success_response({"deleted": 0}, message="Shogird buyurtmadan ajratildi")


class OrderExpressCreateAPIView(InternalAPIViewMixin, APIView):
    def post(self, request):
        client, _ = Client.objects.get_or_create(
            phone=request.data.get("client_phone"),
            defaults={"first_name": request.data.get("client_name", "")},
        )
        payload = {
            "client_id": client.id,
            "service_id": request.data.get("service_id"),
            "price": request.data.get("price"),
            "address": request.data.get("address", ""),
            "note": request.data.get("note", ""),
        }
        serializer = InternalOrderWriteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()
        return success_response(InternalOrderSerializer(order, context={"request": request}).data, message="Tez buyurtma yaratildi")


class OrderMetaAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        orders = list(Order.objects.all())
        counts = {key: 0 for key in ORDER_STATUS_COLORS}
        for order in orders:
            counts[dashboard_order_status(order)] += 1
        statuses = [
            {"value": "new", "label": "Yangi", "color": ORDER_STATUS_COLORS["new"]},
            {"value": "on_way", "label": "Yo'lda", "color": ORDER_STATUS_COLORS["on_way"]},
            {"value": "in_progress", "label": "Bajarilmoqda", "color": ORDER_STATUS_COLORS["in_progress"]},
            {"value": "completed", "label": "Bajarildi", "color": ORDER_STATUS_COLORS["completed"]},
            {"value": "cancelled", "label": "Bekor", "color": ORDER_STATUS_COLORS["cancelled"]},
            {"value": "delayed", "label": "Kechiktirildi", "color": ORDER_STATUS_COLORS["delayed"]},
        ]
        return success_response(
            {
                "tabs": [{"key": "all", "label": "Barchasi", "count": len(orders)}]
                + [{"key": item["value"], "label": item["label"], "count": counts.get(item["value"], 0), "color": item["color"]} for item in statuses],
                "statuses": statuses,
                "payment_statuses": [
                    {"value": "unpaid", "label": "To'lanmagan", "color": "#F59E0B"},
                    {"value": "paid", "label": "To'langan", "color": "#16A34A"},
                    {"value": "refunded", "label": "Qaytarilgan", "color": "#64748B"},
                ],
                "cancellation_reasons": [{"value": reason, "label": reason} for reason in ("Mijoz bekor qildi", "Narx kelishilmadi", "Boshqa sabab")],
                "views": [
                    {"value": "table", "label": "Jadval"},
                    {"value": "card", "label": "Kartochka"},
                    {"value": "board", "label": "Board"},
                ],
            }
        )


class OrderBoardAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        limit = parse_limit(request, default=20)
        queryset = Order.objects.select_related("client", "master", "service", "service__category").all()
        queryset = filter_by_category(queryset, request, field="service__category")
        columns = []
        labels = {
            "new": "Yangi",
            "on_way": "Yo'lda",
            "in_progress": "Bajarilmoqda",
            "completed": "Bajarildi",
            "cancelled": "Bekor",
            "delayed": "Kechiktirildi",
        }
        for key, label in labels.items():
            items = [order for order in queryset if dashboard_order_status(order) == key]
            columns.append(
                {
                    "status": key,
                    "label": label,
                    "color": ORDER_STATUS_COLORS.get(key),
                    "count": len(items),
                    "items": InternalOrderSerializer(items[:limit], many=True, context={"request": request}).data,
                }
            )
        return success_response({"columns": columns})


class OrderExportAPIView(InternalAPIViewMixin, APIView):
    def get(self, request):
        orders = Order.objects.select_related("client", "master", "service", "service__category").all()
        orders = filter_by_category(orders, request, field="service__category")
        return success_response(InternalOrderSerializer(orders, many=True, context={"request": request}).data)
