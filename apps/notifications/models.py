from django.db import models

from apps.common.models import TimeStampedUUIDModel


class Notification(TimeStampedUUIDModel):
    ROLE_CHOICES = (("client", "Client"), ("master", "Master"))
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, null=True, blank=True)
    master = models.ForeignKey("accounts.Master", on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title
