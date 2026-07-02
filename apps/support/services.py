import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.support.models import SupportChat, SupportMessage


logger = logging.getLogger(__name__)


def support_group(role, user_id):
    return f"support_{role}_{user_id}"


def support_admin_group():
    return "support_admin"


def get_or_create_support_chat(user):
    role = getattr(user, "role", None)
    if role == "master":
        chat, _ = SupportChat.objects.get_or_create(
            master=user,
            defaults={"participant_role": "master"},
        )
        return chat
    if role == "client":
        chat, _ = SupportChat.objects.get_or_create(
            client=user,
            defaults={"participant_role": "client"},
        )
        return chat
    return None


def chat_group(chat):
    participant = chat.participant
    if not participant:
        return None
    return support_group(chat.participant_role, participant.id)


def user_can_access_chat(user, chat):
    if getattr(user, "is_staff", False):
        return True
    role = getattr(user, "role", None)
    if role == "master":
        return chat.participant_role == "master" and chat.master_id == user.id
    if role == "client":
        return chat.participant_role == "client" and chat.client_id == user.id
    return False


def with_latest_support_message(queryset):
    latest_message = SupportMessage.objects.filter(chat_id=OuterRef("pk")).order_by("-created_at", "-id")
    return queryset.annotate(
        last_message_id=Subquery(latest_message.values("id")[:1]),
        last_message_created_at=Subquery(latest_message.values("created_at")[:1]),
    )


def attach_latest_support_messages(chats):
    message_ids = [chat.last_message_id for chat in chats if getattr(chat, "last_message_id", None)]
    messages_by_id = SupportMessage.objects.select_related("client", "master", "admin").in_bulk(message_ids)
    for chat in chats:
        chat._last_message = messages_by_id.get(getattr(chat, "last_message_id", None))
    return chats


def touch_chat(chat, increment_unread=False):
    chat.updated_at = timezone.now()
    update_fields = ["updated_at"]
    if increment_unread:
        chat.unread_by_admin = chat.unread_by_admin + 1
        update_fields.append("unread_by_admin")
    chat.save(update_fields=update_fields)


def create_support_message(chat, sender, content, attachment=None):
    role = getattr(sender, "role", None)
    from_participant = role in {"client", "master"}
    message_kwargs = {
        "chat": chat,
        "sender_role": role if from_participant else "admin",
        "message": content,
        "attachment": attachment,
    }
    if role == "master":
        message_kwargs["master"] = sender
    elif role == "client":
        message_kwargs["client"] = sender
    else:
        message_kwargs["admin"] = sender
        if chat.participant_role == "master":
            message_kwargs["master_id"] = chat.master_id
        else:
            message_kwargs["client_id"] = chat.client_id

    message = SupportMessage.objects.create(**message_kwargs)
    touch_chat(chat, increment_unread=from_participant)
    return message


def mark_chat_read_by_admin(chat):
    if not chat.unread_by_admin:
        return False
    chat.unread_by_admin = 0
    chat.updated_at = timezone.now()
    chat.save(update_fields=["unread_by_admin", "updated_at"])
    return True


def support_payload(message):
    from apps.support.serializers import SupportMessageSerializer

    return SupportMessageSerializer(message).data


def support_chat_payload(chat):
    from apps.support.serializers import SupportChatSerializer

    return SupportChatSerializer(chat).data


def broadcast_admin_update(chat):
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("Support admin update skipped: channel layer is unavailable for chat_id=%s", chat.id)
        return
    try:
        async_to_sync(channel_layer.group_send)(
            support_admin_group(),
            {
                "type": "chat.update",
                "chat_id": str(chat.id),
                "participant_role": chat.participant_role,
                "unread_by_admin": chat.unread_by_admin,
                "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
            },
        )
    except Exception:
        logger.exception("Failed to broadcast support admin update for chat_id=%s", chat.id)
        return


def broadcast_support_message(message):
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning("Support message broadcast skipped: channel layer is unavailable for message_id=%s", message.id)
        return
    chat = message.chat
    if not chat:
        logger.warning("Support message broadcast skipped: message_id=%s has no chat", message.id)
        return
    group = chat_group(chat)
    if not group:
        logger.warning("Support message broadcast skipped: chat_id=%s has no participant group", chat.id)
        return
    payload = support_payload(message)
    try:
        async_to_sync(channel_layer.group_send)(
            group,
            {"type": "chat.message", "message": payload, "payload": payload},
        )
    except Exception:
        logger.exception(
            "Failed to broadcast support message message_id=%s chat_id=%s group=%s",
            message.id,
            chat.id,
            group,
        )
        return
    broadcast_admin_update(chat)
