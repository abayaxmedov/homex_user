from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


def notification_group(role, user_id):
    return f"notifications_{role}_{user_id}"


def notification_payload(notification):
    return NotificationSerializer(notification).data


def broadcast_notification(notification, event_type="notification.created"):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    user_id = notification.master_id if notification.role == "master" else notification.client_id
    if not user_id:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            notification_group(notification.role, user_id),
            {
                "type": "notification.event",
                "event": event_type,
                "payload": notification_payload(notification),
            },
        )
    except Exception:
        return


def broadcast_notification_read_all(role, user_id):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    try:
        async_to_sync(channel_layer.group_send)(
            notification_group(role, user_id),
            {
                "type": "notification.event",
                "event": "notification.read_all",
                "payload": {"role": role, "user_id": str(user_id)},
            },
        )
    except Exception:
        return


def create_notification(*, role, title, body="", data=None, client=None, master=None):
    notification = Notification.objects.create(
        role=role,
        client=client,
        master=master,
        title=title,
        body=body,
        data=data or {},
    )
    broadcast_notification(notification)
    return notification
