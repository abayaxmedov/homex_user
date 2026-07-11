import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q

from apps.common.realtime import json_safe
from apps.orders.models import STATUS_TAB, Order, OrderStatus


logger = logging.getLogger(__name__)


DASHBOARD_ORDERS_GROUP = "dashboard_orders"
MASTER_STATUS_ORDER_STATUSES = (
    OrderStatus.NEW,
    OrderStatus.ACCEPTED,
    OrderStatus.ON_WAY,
    OrderStatus.ARRIVED,
)


def dashboard_orders_group():
    return DASHBOARD_ORDERS_GROUP


def master_status_value(master):
    if master is None:
        return None
    if getattr(master, "is_blocked", False):
        return "blocked"
    if not getattr(master, "is_active", True):
        return "inactive"
    if getattr(master, "is_online", False) and getattr(master, "is_available", False):
        return "active"
    if getattr(master, "is_online", False):
        return "busy"
    return "inactive"


def master_realtime_payload(master):
    if master is None:
        return None
    return {
        "id": str(master.id),
        "full_name": getattr(master, "full_name", str(master)),
        "phone": getattr(master, "phone", ""),
        "status": master_status_value(master),
        "is_online": master.is_online,
        "is_available": master.is_available,
        "is_active": master.is_active,
        "is_blocked": master.is_blocked,
        "approval_status": master.approval_status,
        "last_location_at": master.last_location_at,
        "updated_at": master.updated_at,
    }


def order_realtime_payload(order, *, old_status=None, old_master_id=None):
    active_assignments = (
        order.assigned_masters.filter(is_active=True)
        .select_related("master")
        .order_by("created_at")
    )
    return {
        "order_id": str(order.id),
        "status": order.status,
        "status_label": order.get_status_display(),
        "old_status": old_status,
        "status_tab": STATUS_TAB.get(order.status, ""),
        "master_id": str(order.master_id) if order.master_id else None,
        "old_master_id": str(old_master_id) if old_master_id else None,
        "master_status": master_status_value(order.master),
        "master": master_realtime_payload(order.master),
        "assigned_master_ids": [str(row.master_id) for row in active_assignments],
        "assigned_masters": [master_realtime_payload(row.master) for row in active_assignments],
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def _group_send(event_type, payload):
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("Dashboard order broadcast skipped: channel layer is unavailable event=%s", event_type)
        return
    try:
        async_to_sync(channel_layer.group_send)(
            dashboard_orders_group(),
            {
                "type": "dashboard.order.event",
                "event": event_type,
                "payload": json_safe(payload),
            },
        )
    except Exception:
        logger.exception("Failed to broadcast dashboard order event=%s", event_type)


def broadcast_dashboard_order(order, event_type, *, old_status=None, old_master_id=None):
    order = (
        Order.objects.select_related("master")
        .filter(pk=order.pk)
        .first()
    )
    if not order:
        return
    _group_send(
        event_type,
        order_realtime_payload(order, old_status=old_status, old_master_id=old_master_id),
    )


def broadcast_dashboard_master_status(master):
    order_ids = list(
        Order.objects.filter(
            Q(master=master) | Q(assigned_masters__master=master, assigned_masters__is_active=True),
            status__in=MASTER_STATUS_ORDER_STATUSES,
        )
        .distinct()
        .values_list("id", flat=True)
    )
    _group_send(
        "master.status_changed",
        {
            "master_id": str(master.id),
            "master_status": master_status_value(master),
            "master": master_realtime_payload(master),
            "order_ids": [str(order_id) for order_id in order_ids],
            "updated_at": master.updated_at,
        },
    )
