import json

from channels.generic.websocket import AsyncWebsocketConsumer


class ClientSupportConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "role", None) != "client":
            await self.close()
            return
        self.group_name = f"support_client_{user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "support.message", "payload": json.loads(text_data or "{}")},
        )

    async def support_message(self, event):
        await self.send(text_data=json.dumps(event["payload"]))
