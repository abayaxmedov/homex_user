from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.notifications.services import create_notification
from apps.orders.models import STATUS_TAB, Order, OrderStatus
from apps.orders.tracking import ensure_tracking


# Client-facing copy for each status transition.
STATUS_MESSAGES = {
    OrderStatus.ACCEPTED: ("Buyurtma qabul qilindi", "Usta buyurtmangizni qabul qildi"),
    OrderStatus.ON_WAY: ("Usta yo'lda", "Usta buyurtma manziliga yo'lga chiqdi"),
    OrderStatus.ARRIVED: ("Usta yetib keldi", "Usta buyurtma manziliga yetib keldi"),
    OrderStatus.COMPLETED: ("Buyurtma yakunlandi", "Usta buyurtmani yakunladi"),
    OrderStatus.CANCELLED: ("Buyurtma bekor qilindi", "Buyurtmangiz bekor qilindi"),
    OrderStatus.REJECTED: ("Buyurtma rad etildi", "Usta buyurtmani rad etdi"),
}

# Master-facing copy (works for the lead master and assistants alike).
MASTER_STATUS_MESSAGES = {
    OrderStatus.ACCEPTED: "Buyurtma qabul qilindi",
    OrderStatus.ON_WAY: "Buyurtma: yo'lda",
    OrderStatus.ARRIVED: "Buyurtma: manzilga yetib borildi",
    OrderStatus.COMPLETED: "Buyurtma yakunlandi",
    OrderStatus.CANCELLED: "Buyurtma bekor qilindi",
    OrderStatus.REJECTED: "Buyurtma rad etildi",
}


@receiver(post_save, sender=Order)
def sync_order_status(sender, instance, created, **kwargs):
    """Push every order status change to the client's NOTIFICATION socket.

    Notifications are the single realtime channel for status: any code path that
    changes the status (master REST endpoints, the dashboard/admin assign & status
    flows, client cancel, ...) makes the client see the new status live without a
    refresh, and also fires an FCM push. Nothing is persisted — the notification
    is realtime-only (see ``create_notification``).

    The tracking socket is intentionally NOT touched here: it carries only the
    master's live lat/lng while the master is on the way to the client.
    """
    if created:
        ensure_tracking(instance)
        instance._loaded_status = instance.status
        return

    previous_status = getattr(instance, "_loaded_status", None)
    if previous_status is not None and previous_status != instance.status:
        ensure_tracking(instance)
        _notify_status_change(instance)

    # Refresh the marker so a later save on the same instance compares against
    # the up-to-date status instead of re-broadcasting the same transition.
    instance._loaded_status = instance.status


def _notify_status_change(order):
    reason = ""
    if order.status == OrderStatus.CANCELLED:
        reason = order.cancel_reason or ""
    elif order.status == OrderStatus.REJECTED:
        reason = order.rejected_reason or ""
    data = {
        "order_id": str(order.id),
        "status": order.status,
        "status_label": OrderStatus(order.status).label,
        "status_tab": STATUS_TAB.get(order.status, ""),
    }

    # Client (the customer) — client-facing copy.
    client_title, client_body = STATUS_MESSAGES.get(order.status, ("Buyurtma holati yangilandi", ""))
    create_notification(
        role="client",
        client=order.client,
        title=client_title,
        body=reason or client_body,
        data=data,
        event="order.status",
    )

    # Every active assigned master (lead + assistants) — so the whole crew stays
    # in sync in realtime, including on admin-initiated cancel/reject.
    master_title = MASTER_STATUS_MESSAGES.get(order.status, "Buyurtma holati yangilandi")
    for master in _active_masters(order):
        create_notification(
            role="master",
            master=master,
            title=master_title,
            body=reason,
            data=data,
            event="order.status",
        )


def _active_masters(order):
    """The lead master plus every still-active assigned master, de-duplicated."""
    masters = {}
    if order.master_id:
        masters[order.master_id] = order.master
    for link in order.assigned_masters.filter(is_active=True).select_related("master"):
        masters[link.master_id] = link.master
    return list(masters.values())
