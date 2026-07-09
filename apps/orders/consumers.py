import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from apps.common.geo import to_decimal
from apps.orders.models import Order
from apps.orders.tracking import (
    ensure_tracking,
    json_safe,
    refresh_master_order_tracking,
    tracking_group,
    tracking_payload,
)


logger = logging.getLogger(__name__)


@database_sync_to_async
def client_can_track(user, order_id):
    return Order.objects.filter(id=order_id, client=user).exists()


@database_sync_to_async
def client_tracking_snapshot(user, order_id):
    order = Order.objects.select_related("master", "tracking", "client").filter(id=order_id, client=user).first()
    if not order:
        return None
    ensure_tracking(order)
    return tracking_payload(order)


@database_sync_to_async
def persist_master_location(master, payload):
    """Save the master's location and prepare tracking broadcasts.

    Returns ``None`` when lat/lng is missing/invalid or an explicit order_id
    does not belong to this master. Otherwise returns the ack for the master
    plus one broadcast per affected order (all active orders when the app
    streams bare lat/lng without an order_id).
    """
    lat = to_decimal(payload.get("lat"))
    lng = to_decimal(payload.get("lng"))
    if lat is None or lng is None:
        return None

    master.lat = lat
    master.lng = lng
    master.last_location_at = timezone.now()
    master.is_online = True
    master.save(update_fields=["lat", "lng", "last_location_at", "is_online", "updated_at"])

    order_id = payload.get("order_id")
    updates = refresh_master_order_tracking(
        master,
        lat,
        lng,
        order_id=order_id,
        distance_hint=payload.get("distance_km"),
        eta_hint=payload.get("eta_minutes"),
        raw_payload=payload,
    )
    if order_id and not updates:
        return None

    if order_id:
        ack = updates[0][1]
    else:
        ack = {
            "lat": str(lat),
            "lng": str(lng),
            "distance_km": payload.get("distance_km"),
            "eta_minutes": payload.get("eta_minutes"),
            "orders_notified": len(updates),
        }
    return {
        "ack": ack,
        "broadcasts": [(tracking_group(order.id), order_payload) for order, order_payload in updates],
    }


class MasterTrackingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "role", None) != "master":
            await self.close()
            return
        self.group_name = f"master_tracking_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # A bad frame must not kill the socket (same policy as the support chat).
        try:
            payload = json.loads(text_data or "{}")
        except Exception:
            logger.warning("Invalid master tracking WebSocket payload received", exc_info=True)
            await self.send(text_data=json.dumps({"type": "error", "detail": "invalid JSON payload"}))
            return
        result = await persist_master_location(self.scope["user"], payload)
        if not result:
            await self.send(
                text_data=json.dumps({"type": "error", "detail": "lat/lng required (or order not found)"})
            )
            return
        for group_name, group_payload in result["broadcasts"]:
            await self.channel_layer.group_send(
                group_name,
                {"type": "tracking.update", "event": "master.location", "payload": json_safe(group_payload)},
            )
        await self.send(
            text_data=json.dumps({"type": "master.location.saved", "data": result["ack"]}, cls=DjangoJSONEncoder)
        )


class ClientTrackingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "role", None) != "client":
            await self.close()
            return
        order_id = self.scope["url_route"]["kwargs"]["order_id"]
        if not await client_can_track(user, order_id):
            await self.close()
            return
        self.order_id = order_id
        self.group_name = tracking_group(order_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        snapshot = await client_tracking_snapshot(user, order_id)
        if snapshot:
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "tracking.snapshot",
                        "data": snapshot,
                    },
                    cls=DjangoJSONEncoder,
                )
            )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def location_update(self, event):
        payload = event["payload"]
        await self.send(
            text_data=json.dumps(
                {
                    "type": "master.location",
                    "data": payload,
                },
                cls=DjangoJSONEncoder,
            )
        )

    async def tracking_update(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": event.get("event", "tracking.update"),
                    "data": event["payload"],
                },
                cls=DjangoJSONEncoder,
            )
        )
