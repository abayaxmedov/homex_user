from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.orders.models import Order
from apps.orders.tracking import ensure_tracking


@receiver(post_save, sender=Order)
def create_order_tracking(sender, instance, created, **kwargs):
    if created:
        ensure_tracking(instance)
