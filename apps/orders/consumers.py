import json

from channels.generic.websocket import AsyncWebsocketConsumer


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
        order_id = payload.get("order_id")
        if order_id:
            await self.channel_layer.group_send(
                f"order_tracking_{order_id}",
                {"type": "location.update", "payload": payload},
            )


class ClientTrackingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "role", None) != "client":
            await self.close()
            return
        self.group_name = f"order_tracking_{self.scope['url_route']['kwargs']['order_id']}"
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
                    "lat": payload.get("lat"),
                    "lng": payload.get("lng"),
                    "distance_km": payload.get("distance_km"),
                    "eta_minutes": payload.get("eta_minutes"),
                }
            )
        )
