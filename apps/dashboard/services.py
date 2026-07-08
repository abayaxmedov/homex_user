from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from apps.accounts.models import Master
from apps.dashboard.models import DashboardCompanyExpense, DashboardWarehouseExpense
from apps.orders.models import Order, OrderStatus
from apps.wallet.models import MasterExpense


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


def default_target_date():
    return timezone.localdate()


def money(value) -> int:
    return int(value or 0)


def format_uzs(value) -> str:
    return f"{money(value):,} so'm"


def percent_change(current: int | Decimal, previous: int | Decimal) -> tuple[int, str]:
    current = Decimal(current or 0)
    previous = Decimal(previous or 0)
    if previous == 0:
        return (100 if current > 0 else 0), "up" if current > 0 else "flat"
    diff = ((current - previous) / previous) * 100
    direction = "up" if diff > 0 else "down" if diff < 0 else "flat"
    return int(abs(diff)), direction


def get_stats(target_date):
    previous_date = target_date - timedelta(days=1)

    today_orders = Order.objects.filter(created_at__date=target_date).count()
    yesterday_orders = Order.objects.filter(created_at__date=previous_date).count()

    active_masters = Master.objects.filter(is_active=True, is_online=True).count()
    previous_active_masters = active_masters

    daily_income = (
        Order.objects.filter(status=OrderStatus.COMPLETED, updated_at__date=target_date)
        .aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0")
    )
    yesterday_income = (
        Order.objects.filter(status=OrderStatus.COMPLETED, updated_at__date=previous_date)
        .aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0")
    )

    daily_expense = (
        (MasterExpense.objects.filter(date=target_date).aggregate(total=Sum("amount"))["total"] or Decimal("0"))
        + (DashboardCompanyExpense.objects.filter(date=target_date).aggregate(total=Sum("amount"))["total"] or Decimal("0"))
        + (DashboardWarehouseExpense.objects.filter(date=target_date).aggregate(total=Sum("amount"))["total"] or Decimal("0"))
    )
    yesterday_expense = (
        (MasterExpense.objects.filter(date=previous_date).aggregate(total=Sum("amount"))["total"] or Decimal("0"))
        + (DashboardCompanyExpense.objects.filter(date=previous_date).aggregate(total=Sum("amount"))["total"] or Decimal("0"))
        + (DashboardWarehouseExpense.objects.filter(date=previous_date).aggregate(total=Sum("amount"))["total"] or Decimal("0"))
    )

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
            accepted=Count("id", filter=Q(status=OrderStatus.ACCEPTED)),
            on_way=Count("id", filter=Q(status=OrderStatus.ON_WAY)),
            arrived=Count("id", filter=Q(status=OrderStatus.ARRIVED)),
            completed=Count("id", filter=Q(status=OrderStatus.COMPLETED)),
            cancelled=Count("id", filter=Q(status=OrderStatus.CANCELLED)),
            rejected=Count("id", filter=Q(status=OrderStatus.REJECTED)),
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
                "accepted": row.get("accepted", 0),
                "on_way": row.get("on_way", 0),
                "arrived": row.get("arrived", 0),
                "completed": row.get("completed", 0),
                "cancelled": row.get("cancelled", 0),
                "rejected": row.get("rejected", 0),
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
    master_expense_rows = (
        MasterExpense.objects.filter(date__year=year)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(expense=Sum("amount"))
    )
    company_expense_rows = (
        DashboardCompanyExpense.objects.filter(date__year=year)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(expense=Sum("amount"))
    )
    warehouse_expense_rows = (
        DashboardWarehouseExpense.objects.filter(date__year=year)
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(expense=Sum("amount"))
    )
    income_by_month = {row["month"].month: row["income"] or Decimal("0") for row in income_rows}
    expense_by_month = {}
    for rows in (master_expense_rows, company_expense_rows, warehouse_expense_rows):
        for row in rows:
            month = row["month"].month
            expense_by_month[month] = expense_by_month.get(month, Decimal("0")) + (row["expense"] or Decimal("0"))
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
