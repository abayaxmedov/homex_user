import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from apps.common.geo import distance_km, eta_minutes, to_decimal
from apps.orders.models import Order, OrderTracking


@database_sync_to_async
def client_can_track(user, order_id):
    return Order.objects.filter(id=order_id, client=user).exists()


@database_sync_to_async
def persist_master_location(master, payload):
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
    if not order_id:
        return {
            "lat": str(lat),
            "lng": str(lng),
            "distance_km": payload.get("distance_km"),
            "eta_minutes": payload.get("eta_minutes"),
        }

    order = Order.objects.filter(id=order_id, master=master).first()
    if not order:
        return None

    calculated_distance = payload.get("distance_km")
    if calculated_distance in (None, ""):
        calculated_distance = distance_km(lat, lng, order.lat, order.lng)
    calculated_eta = payload.get("eta_minutes")
    if calculated_eta in (None, ""):
        calculated_eta = eta_minutes(calculated_distance)

    tracking, _ = OrderTracking.objects.update_or_create(
        order=order,
        defaults={
            "master_lat": lat,
            "master_lng": lng,
            "distance_km": calculated_distance,
            "eta_minutes": calculated_eta,
            "raw_payload": payload,
        },
    )
    return {
        "order_id": str(order.id),
        "lat": str(tracking.master_lat),
        "lng": str(tracking.master_lng),
        "distance_km": float(tracking.distance_km) if tracking.distance_km is not None else None,
        "eta_minutes": tracking.eta_minutes,
        "updated_at": tracking.updated_at.isoformat(),
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
        payload = json.loads(text_data or "{}")
        location = await persist_master_location(self.scope["user"], payload)
        if not location:
            return
        order_id = payload.get("order_id")
        if order_id:
            await self.channel_layer.group_send(
                f"order_tracking_{order_id}",
                {"type": "location.update", "payload": location},
            )
        await self.send(text_data=json.dumps({"type": "master.location.saved", "data": location}))


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
        self.group_name = f"order_tracking_{order_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

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
                }
            )
        )
