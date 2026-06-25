import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer
from apps.notifications.services import notification_group


@database_sync_to_async
def mark_notification_read(user, notification_id):
    queryset = Notification.objects.filter(pk=notification_id)
    if getattr(user, "role", None) == "master":
        queryset = queryset.filter(master=user)
    else:
        queryset = queryset.filter(client=user)
    notification = queryset.first()
    if not notification:
        return None
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return NotificationSerializer(notification).data


class BaseNotificationConsumer(AsyncWebsocketConsumer):
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

    async def receive(self, text_data=None, bytes_data=None):
        payload = json.loads(text_data or "{}")
        if payload.get("action") == "read" and payload.get("id"):
            notification = await mark_notification_read(self.scope["user"], payload["id"])
            if notification:
                await self.send(text_data=json.dumps({"type": "notification.read", "data": notification}))

    async def notification_event(self, event):
        await self.send(text_data=json.dumps({"type": event["event"], "data": event["payload"]}))


class ClientNotificationConsumer(BaseNotificationConsumer):
    role = "client"


class MasterNotificationConsumer(BaseNotificationConsumer):
    role = "master"
