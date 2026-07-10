from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Master
from apps.dashboard.realtime import broadcast_dashboard_master_status


@receiver(post_save, sender=Master)
def sync_master_status(sender, instance, created, **kwargs):
    if created:
        instance._loaded_status_fields = instance.status_fields()
        return

    previous = getattr(instance, "_loaded_status_fields", None)
    current = instance.status_fields()
    if previous is not None and previous != current:
        broadcast_dashboard_master_status(instance)
    instance._loaded_status_fields = current
