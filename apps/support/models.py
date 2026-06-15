from django.db import models

from apps.common.models import TimeStampedUUIDModel


class SupportMessage(TimeStampedUUIDModel):
    ROLE_CHOICES = (("client", "Client"), ("master", "Master"), ("admin", "Admin"))
    sender_role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, null=True, blank=True)
    master = models.ForeignKey("accounts.Master", on_delete=models.CASCADE, null=True, blank=True)
    message = models.TextField()
    attachment = models.FileField(upload_to="support/", null=True, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at",)
