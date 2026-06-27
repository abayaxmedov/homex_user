from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.accounts.serializers import MasterSummarySerializer
from apps.common.geo import distance_km, eta_minutes
from apps.orders.models import OrderStatus, OrderTracking


TRACKING_STEPS = (
    {"order_status": OrderStatus.NEW, "key": "searching_master", "label": "Usta qidirilmoqda"},
    {"order_status": OrderStatus.ACCEPTED, "key": "master_on_way", "label": "Usta yo'lda"},
    {"order_status": OrderStatus.IN_PROGRESS, "key": "master_working", "label": "Usta ishlamoqda"},
    {"order_status": OrderStatus.COMPLETED, "key": "master_finished", "label": "Usta ishni tugatgan"},
)

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
            "events": ["tracking.snapshot", "tracking.update", "master.location"],
        },
    }


def tracking_group(order_id):
    return f"order_tracking_{order_id}"


def broadcast_tracking(order, payload=None, event_type="tracking.update"):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            tracking_group(order.id),
            {
                "type": "tracking.update",
                "event": event_type,
                "payload": payload or tracking_payload(order),
            },
        )
    except Exception:
        return
