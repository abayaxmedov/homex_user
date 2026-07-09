import json

from channels.generic.websocket import AsyncWebsocketConsumer

from apps.notifications.services import notification_group


class BaseNotificationConsumer(AsyncWebsocketConsumer):
    """Realtime-only notification socket.

    Notifications are never persisted (see ``create_notification``), so there is
    no read/unread state and nothing to receive from the client — the socket only
    relays server-pushed events (order status changes, alerts) in realtime.
    """

    role = None

    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "role", None) != self.role:
            await self.close()
            return
        self.group_name = notification_group(self.role, user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_event(self, event):
        await self.send(text_data=json.dumps({"type": event["event"], "data": event["payload"]}))


class ClientNotificationConsumer(BaseNotificationConsumer):
    role = "client"


class MasterNotificationConsumer(BaseNotificationConsumer):
    role = "master"
