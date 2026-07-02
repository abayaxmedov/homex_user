import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.accounts.models import FCMDevice
from apps.integrations.adapters import PushClient
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


logger = logging.getLogger(__name__)


def notification_group(role, user_id):
    return f"notifications_{role}_{user_id}"


def notification_payload(notification):
    return NotificationSerializer(notification).data


def broadcast_notification(notification, event_type="notification.created"):
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning(
            "Notification broadcast skipped: channel layer is unavailable for notification_id=%s",
            notification.id,
        )
        return
    user_id = notification.master_id if notification.role == "master" else notification.client_id
    if not user_id:
        logger.warning("Notification broadcast skipped: notification_id=%s has no target user", notification.id)
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
        logger.exception(
            "Failed to broadcast notification notification_id=%s event_type=%s role=%s user_id=%s",
            notification.id,
            event_type,
            notification.role,
            user_id,
        )
        return


def broadcast_notification_read_all(role, user_id):
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning(
            "Notification read-all broadcast skipped: channel layer is unavailable role=%s user_id=%s",
            role,
            user_id,
        )
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
        logger.exception("Failed to broadcast notification read-all role=%s user_id=%s", role, user_id)
        return


def push_payload(notification):
    payload = {
        "event": "notification.created",
        "notification_id": str(notification.id),
        "role": notification.role,
    }
    payload.update(notification.data or {})
    return payload


def send_push_notification(notification):
    target = notification.master if notification.role == "master" else notification.client
    if not target or not target.notifications_enabled or not target.push_enabled:
        return None

    device_filter = {"role": notification.role, "is_active": True}
    if notification.role == "master":
        device_filter["master"] = target
    else:
        device_filter["client"] = target

    tokens = list(FCMDevice.objects.filter(**device_filter).values_list("token", flat=True))
    if not tokens:
        return None

    try:
        return PushClient().send_many(tokens, notification.title, notification.body, data=push_payload(notification))
    except Exception:
        logger.exception(
            "Failed to send push notification notification_id=%s role=%s token_count=%s",
            notification.id,
            notification.role,
            len(tokens),
        )
        return None


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
    send_push_notification(notification)
    return notification
