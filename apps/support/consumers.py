import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.support.models import SupportMessage
from apps.support.serializers import SupportMessageSerializer
from apps.support.services import support_group


@database_sync_to_async
def create_support_message(user, message):
    if getattr(user, "role", None) == "master":
        instance = SupportMessage.objects.create(sender_role="master", master=user, message=message)
    else:
        instance = SupportMessage.objects.create(sender_role="client", client=user, message=message)
    return SupportMessageSerializer(instance).data


class BaseSupportConsumer(AsyncWebsocketConsumer):
    role = None

    async def connect(self):
        user = self.scope.get("user")
        if not user or getattr(user, "role", None) != self.role:
            await self.close()
            return
        self.group_name = support_group(self.role, user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        payload = json.loads(text_data or "{}")
        message = (payload.get("message") or "").strip()
        if not message:
            return
        data = await create_support_message(self.scope["user"], message)
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "support.message", "payload": data},
        )

    async def support_message(self, event):
        await self.send(text_data=json.dumps({"type": "support.message", "data": event["payload"]}))


class ClientSupportConsumer(BaseSupportConsumer):
    role = "client"


class MasterSupportConsumer(BaseSupportConsumer):
    role = "master"
