from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.orders.models import Order
from apps.orders.tracking import broadcast_tracking, ensure_tracking


@receiver(post_save, sender=Order)
def sync_order_tracking(sender, instance, created, **kwargs):
    """Keep the client's tracking socket in sync with the order lifecycle.

    On creation we make sure a tracking row exists. On every subsequent save we
    compare the current status against the value loaded from the DB and, when it
    changed, push the fresh tracking payload to the client's tracking group.

    This centralizes tracking broadcasts the same way the support chat
    centralizes message broadcasts: any code path that changes the status
    (master REST endpoints, the dashboard "assign master" flow, the internal
    API, the Django admin, ...) notifies the client automatically, instead of
    each caller having to remember to broadcast.
    """
    if created:
        ensure_tracking(instance)
        instance._loaded_status = instance.status
        return

    previous_status = getattr(instance, "_loaded_status", None)
    if previous_status is not None and previous_status != instance.status:
        ensure_tracking(instance)
        broadcast_tracking(instance, event_type="tracking.update")

    # Refresh the marker so a later save on the same instance compares against
    # the up-to-date status instead of re-broadcasting the same transition.
    instance._loaded_status = instance.status
