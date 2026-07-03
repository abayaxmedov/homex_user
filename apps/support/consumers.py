import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.serializers.json import DjangoJSONEncoder

from apps.support.models import SupportChat
from apps.support.serializers import SupportMessageSerializer
from apps.support.services import (
    chat_group,
    create_support_message,
    get_or_create_support_chat,
    mark_chat_read_by_admin,
    support_admin_group,
    support_group,
    user_can_access_chat,
)


logger = logging.getLogger(__name__)


def ws_json_dumps(payload):
    return json.dumps(payload, cls=DjangoJSONEncoder)


async def send_json_payload(consumer, payload):
    await consumer.send(text_data=ws_json_dumps(payload))


@database_sync_to_async
def get_user_chat(user):
    return get_or_create_support_chat(user)


@database_sync_to_async
def get_allowed_chat(chat_id, user):
    try:
        chat = SupportChat.objects.select_related("client", "master").get(pk=chat_id)
    except SupportChat.DoesNotExist:
        return None
    if not user_can_access_chat(user, chat):
        return None
    return chat


@database_sync_to_async
def serialize_history(chat_id):
    messages = list(
        SupportChat.objects.get(pk=chat_id)
        .messages.select_related("client", "master", "admin")
        .order_by("created_at")
    )
    return SupportMessageSerializer(messages, many=True).data


@database_sync_to_async
def create_ws_message(chat_id, user, content):
    chat = SupportChat.objects.select_related("client", "master").get(pk=chat_id)
    message = create_support_message(chat=chat, sender=user, content=content)
    return {
        "message": SupportMessageSerializer(message).data,
        "chat_id": str(chat.id),
        "participant_role": chat.participant_role,
        "unread_by_admin": chat.unread_by_admin,
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
    }


@database_sync_to_async
def mark_read(chat_id):
    chat = SupportChat.objects.get(pk=chat_id)
    changed = mark_chat_read_by_admin(chat)
    return {
        "changed": changed,
        "chat_id": str(chat.id),
        "participant_role": chat.participant_role,
        "unread_by_admin": chat.unread_by_admin,
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
    }


def _is_authenticated(user):
    return bool(user and getattr(user, "is_authenticated", False))


class BaseSupportConsumer(AsyncWebsocketConsumer):
    role = None

    async def connect(self):
        user = self.scope.get("user")
        if not _is_authenticated(user) or getattr(user, "role", None) != self.role:
            await self.close()
            return
        self.chat = await get_user_chat(user)
        if not self.chat:
            await self.close()
            return
        self.chat_id = str(self.chat.id)
        self.group_name = support_group(self.role, user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        history = await serialize_history(self.chat_id)
        await send_json_payload(self, {"type": "history", "messages": history, "chat_id": self.chat_id})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or "{}")
        except Exception:
            logger.warning(
                "Invalid support WebSocket payload received for chat_id=%s",
                self.chat_id,
                exc_info=True,
            )
            return
        content = (payload.get("content") or payload.get("message") or payload.get("text") or "").strip()
        if not content:
            await send_json_payload(self, {"type": "error", "detail": "content (or message) required"})
            return
        data = await create_ws_message(self.chat_id, self.scope["user"], content)
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "chat.message", "message": data["message"], "payload": data["message"]},
        )
        await self.channel_layer.group_send(
            support_admin_group(),
            {
                "type": "chat.update",
                "chat_id": data["chat_id"],
                "participant_role": data["participant_role"],
                "unread_by_admin": data["unread_by_admin"],
                "updated_at": data["updated_at"],
            },
        )

    async def chat_message(self, event):
        message = event.get("message") or event.get("payload")
        await send_json_payload(self, {"type": "message", "message": message, "data": message})


class ClientSupportConsumer(BaseSupportConsumer):
    role = "client"


class MasterSupportConsumer(BaseSupportConsumer):
    role = "master"


class AdminSupportChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not _is_authenticated(user) or not getattr(user, "is_staff", False):
            await self.close()
            return
        raw_chat_id = self.scope["url_route"]["kwargs"].get("chat_id")
        self.chat = await get_allowed_chat(raw_chat_id, user)
        if not self.chat:
            await self.close()
            return
        self.chat_id = str(self.chat.id)
        self.group_name = chat_group(self.chat)
        if not self.group_name:
            await self.close()
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        read_state = await mark_read(self.chat_id)
        if read_state["changed"]:
            await self.channel_layer.group_send(
                support_admin_group(),
                {
                    "type": "chat.update",
                    "chat_id": read_state["chat_id"],
                    "participant_role": read_state["participant_role"],
                    "unread_by_admin": read_state["unread_by_admin"],
                    "updated_at": read_state["updated_at"],
                },
            )
        history = await serialize_history(self.chat_id)
        await send_json_payload(self, {"type": "history", "messages": history, "chat_id": self.chat_id})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        try:
            payload = json.loads(text_data or "{}")
        except Exception:
            logger.warning(
                "Invalid admin support WebSocket payload received for chat_id=%s",
                self.chat_id,
                exc_info=True,
            )
            return
        content = (payload.get("content") or payload.get("message") or payload.get("text") or "").strip()
        if not content:
            await send_json_payload(self, {"type": "error", "detail": "content (or message) required"})
            return
        data = await create_ws_message(self.chat_id, self.scope["user"], content)
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "chat.message", "message": data["message"], "payload": data["message"]},
        )
        await self.channel_layer.group_send(
            support_admin_group(),
            {
                "type": "chat.update",
                "chat_id": data["chat_id"],
                "participant_role": data["participant_role"],
                "unread_by_admin": data["unread_by_admin"],
                "updated_at": data["updated_at"],
            },
        )

    async def chat_message(self, event):
        message = event.get("message") or event.get("payload")
        await send_json_payload(self, {"type": "message", "message": message, "data": message})


class AdminSupportLobbyConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not _is_authenticated(user) or not getattr(user, "is_staff", False):
            await self.close()
            return
        await self.channel_layer.group_add(support_admin_group(), self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(support_admin_group(), self.channel_name)

    async def chat_update(self, event):
        await send_json_payload(self, {"type": "chat.update", **{k: v for k, v in event.items() if k != "type"}})
