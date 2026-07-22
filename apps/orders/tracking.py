import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.accounts.serializers import MasterSummarySerializer
from apps.common.geo import distance_km, eta_minutes
from apps.common.realtime import json_safe  # noqa: F401 (re-exported for consumers)
from apps.orders.models import ACTIVE_ORDER_STATUSES, Order, OrderStatus, OrderTracking


logger = logging.getLogger(__name__)


# Statuses whose orders should keep receiving the master's live location.
ACTIVE_TRACKING_STATUSES = ACTIVE_ORDER_STATUSES


TRACKING_STEPS = (
    {"order_status": OrderStatus.NEW, "key": "searching_master", "label": "Usta qidirilmoqda"},
    {"order_status": OrderStatus.ACCEPTED, "key": "master_accepted", "label": "Usta qabul qildi"},
    {"order_status": OrderStatus.ON_WAY, "key": "master_on_way", "label": "Usta yo'lda"},
    {"order_status": OrderStatus.ARRIVED, "key": "master_arrived", "label": "Usta yetib keldi"},
    # Master finished the work + sent the check (awaiting the client's payment).
    {"order_status": OrderStatus.AWAITING_PAYMENT, "key": "master_finished", "label": "Usta ishni tugatgan"},
    {"order_status": OrderStatus.COMPLETED, "key": "completed", "label": "Buyurtma yakunlandi"},
)

# Statuses where the master's submitted check is viewable/downloadable by the client.
RECEIPT_READY_STATUSES = (OrderStatus.AWAITING_PAYMENT, OrderStatus.COMPLETED)

TERMINAL_STATUS_LABELS = {
    OrderStatus.CANCELLED: ("cancelled", "Buyurtma bekor qilingan"),
    OrderStatus.REJECTED: ("rejected", "Buyurtma rad etilgan"),
}


def ensure_tracking(order):
    tracking, _ = OrderTracking.objects.get_or_create(order=order)
    return tracking


def tracking_state(order):
    current_index = next(
        (index for index, step in enumerate(TRACKING_STEPS) if step["order_status"] == order.status),
        None,
    )
    if current_index is None:
        key, label = TERMINAL_STATUS_LABELS.get(order.status, (order.status, order.get_status_display()))
    else:
        step = TRACKING_STEPS[current_index]
        key = step["key"]
        label = step["label"]

    steps = []
    for index, step in enumerate(TRACKING_STEPS):
        steps.append(
            {
                "key": step["key"],
                "order_status": step["order_status"],
                "label": step["label"],
                "step": index + 1,
                "is_active": current_index == index,
                "is_completed": current_index is not None and index <= current_index,
            }
        )

    return {
        "key": key,
        "label": label,
        "step": current_index + 1 if current_index is not None else None,
        "total_steps": len(TRACKING_STEPS),
        "steps": steps,
    }


def _file_url(file_field):
    return file_field.url if file_field else None


def _receipt_status(order):
    return "approved" if order.receipt_approved_at else "not_ready"


def tracking_payload(order):
    tracking = getattr(order, "tracking", None)
    master = order.master
    master_lat = getattr(tracking, "master_lat", None) or getattr(master, "lat", None)
    master_lng = getattr(tracking, "master_lng", None) or getattr(master, "lng", None)
    calculated_distance = getattr(tracking, "distance_km", None)
    if calculated_distance is None and master_lat is not None and master_lng is not None:
        calculated_distance = distance_km(master_lat, master_lng, order.lat, order.lng)
    calculated_eta = getattr(tracking, "eta_minutes", None) or eta_minutes(calculated_distance)
    state = tracking_state(order)
    return {
        "order_id": order.id,
        "status": order.status,
        "status_label": order.get_status_display(),
        "tracking_status": state["key"],
        "tracking_status_label": state["label"],
        "tracking_step": state["step"],
        "tracking_total_steps": state["total_steps"],
        "tracking_steps": state["steps"],
        "before_photo": _file_url(order.before_photo),
        "completion_photo": _file_url(order.completion_photo),
        "receipt_status": _receipt_status(order),
        "receipt_available": order.status in RECEIPT_READY_STATUSES and bool(order.receipt_approved_at),
        "receipt_download_url": f"/api/v1/client/orders/{order.id}/receipt/download/"
        if order.status in RECEIPT_READY_STATUSES and order.receipt_approved_at
        else None,
        "order_location": {"lat": order.lat, "lng": order.lng, "address": order.address_text},
        "master": MasterSummarySerializer(master).data if master else None,
        "master_contact": {"phone_number": master.phone} if master else None,
        "master_location": {
            "lat": master_lat,
            "lng": master_lng,
            "last_location_at": getattr(master, "last_location_at", None),
        },
        "distance_km": calculated_distance,
        "eta_minutes": calculated_eta,
        "websocket": {
            "client_track": f"/ws/client/track/{order.id}/",
            "master_tracking": "/ws/master/tracking/",
            "auth_header": "Authorization: Bearer {access_token}",
            # Tracking socket carries only the snapshot + the master's live location.
            # Status changes arrive on the notification socket instead.
            "events": ["tracking.snapshot", "master.location"],
        },
    }


def tracking_group(order_id):
    return f"order_tracking_{order_id}"


def refresh_master_order_tracking(master, lat, lng, *, order_id=None, distance_hint=None, eta_hint=None, raw_payload=None):
    """Persist the master's location on their order(s) and build broadcast payloads.

    With an explicit ``order_id`` only that order is refreshed (the app's
    "I'm on this job" stream). Without it — the app's generic location ping —
    every active (accepted/in-progress) order of this master is refreshed, so
    the client's tracking socket keeps getting realtime updates either way.
    This centralizes the fan-out the same way the support chat centralizes
    message broadcasts. Returns a list of ``(order, payload)`` pairs.
    """
    if order_id:
        orders = Order.objects.filter(id=order_id, master=master)
    else:
        orders = Order.objects.filter(master=master, status__in=ACTIVE_TRACKING_STATUSES)

    updates = []
    for order in orders.select_related("master", "client"):
        calculated_distance = distance_hint
        if calculated_distance in (None, ""):
            calculated_distance = distance_km(lat, lng, order.lat, order.lng)
        calculated_eta = eta_hint
        if calculated_eta in (None, ""):
            calculated_eta = eta_minutes(calculated_distance)
        tracking, _ = OrderTracking.objects.update_or_create(
            order=order,
            defaults={
                "master_lat": lat,
                "master_lng": lng,
                "distance_km": calculated_distance,
                "eta_minutes": calculated_eta,
                "raw_payload": raw_payload or {},
            },
        )
        # Populate the reverse cache so tracking_payload() sees the fresh row.
        order.tracking = tracking
        updates.append((order, tracking_payload(order)))
    return updates


def broadcast_tracking(order, payload=None, event_type="tracking.update"):
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("Tracking broadcast skipped: channel layer is unavailable for order_id=%s", order.id)
        return
    try:
        async_to_sync(channel_layer.group_send)(
            tracking_group(order.id),
            {
                "type": "tracking.update",
                "event": event_type,
                "payload": json_safe(payload or tracking_payload(order)),
            },
        )
    except Exception:
        logger.exception("Failed to broadcast tracking update order_id=%s event_type=%s", order.id, event_type)
        return
