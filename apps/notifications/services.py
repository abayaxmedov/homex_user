import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import FCMDevice
from apps.common.realtime import json_safe
from apps.integrations.adapters import PushClient
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


logger = logging.getLogger(__name__)


def notification_group(role, user_id):
    return f"notifications_{role}_{user_id}"


def notification_payload(notification):
    # json_safe: NotificationSerializer's client/master PrimaryKeyRelatedFields
    # return raw UUIDs, which the Redis (msgpack) channel layer cannot pack.
    return json_safe(NotificationSerializer(notification).data)


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


def push_payload(notification, event="notification.created"):
    payload = {
        "event": event,
        "notification_id": str(notification.id),
        "role": notification.role,
    }
    payload.update(notification.data or {})
    return payload


def send_push_notification(notification, event="notification.created"):
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

    title, body, data = notification.title, notification.body, push_payload(notification, event)
    notification_id, role = notification.id, notification.role

    def _send():
        try:
            PushClient().send_many(tokens, title, body, data=data)
        except Exception:
            logger.exception(
                "Failed to send push notification notification_id=%s role=%s token_count=%s",
                notification_id,
                role,
                len(tokens),
            )

    # Defer the irreversible external push until the surrounding DB transaction
    # commits. Status notifications now fire from the Order post_save signal, so a
    # transition that later rolls back (e.g. a failed wallet op inside
    # OrderCompleteSerializer.save()) must NOT leave a permanent, un-recallable
    # "order completed" push on the user's phone. In autocommit (accept/on_way/
    # dashboard) on_commit runs immediately, so realtime behaviour is unchanged.
    transaction.on_commit(_send)
    return None


def create_notification(*, role, title, body="", data=None, client=None, master=None, event="notification.created"):
    """Deliver a notification WITHOUT persisting it.

    App notifications (order status, new-order alerts, reviews...) are ephemeral:
    the client/master only needs the realtime WebSocket event plus an FCM push —
    there is no in-app history to browse. We build an unsaved ``Notification``
    (its UUID pk is populated by the field default) purely to reuse the broadcast
    and push helpers; nothing is written to the database.

    The admin CRM (dashboard) still persists its notifications via its own
    serializer.save() and calls broadcast_notification()/send_push_notification()
    directly, so that path keeps its history.
    """
    notification = Notification(
        role=role,
        client=client,
        master=master,
        title=title,
        body=body,
        data=data or {},
    )
    # The instance is never saved, so auto_now_add never runs; stamp a server time
    # so WS events carry a real created_at (matching the persisted dashboard path).
    notification.created_at = notification.updated_at = timezone.now()
    broadcast_notification(notification, event_type=event)
    send_push_notification(notification, event=event)
    return notification
