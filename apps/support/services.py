from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.support.serializers import SupportMessageSerializer


def support_group(role, user_id):
    return f"support_{role}_{user_id}"


def support_payload(message):
    return SupportMessageSerializer(message).data


def broadcast_support_message(message):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    role = message.sender_role
    user_id = message.master_id if role == "master" else message.client_id
    if not user_id:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            support_group(role, user_id),
            {"type": "support.message", "payload": support_payload(message)},
        )
    except Exception:
        return
