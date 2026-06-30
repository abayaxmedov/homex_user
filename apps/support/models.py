from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedUUIDModel


class SupportChat(TimeStampedUUIDModel):
    PARTICIPANT_CHOICES = (("client", "Client"), ("master", "Master"))
    participant_role = models.CharField(max_length=20, choices=PARTICIPANT_CHOICES)
    client = models.OneToOneField(
        "accounts.Client",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="support_chat",
    )
    master = models.OneToOneField(
        "accounts.Master",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="support_chat",
    )
    unread_by_admin = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=("participant_role", "updated_at")),
        ]

    @property
    def participant(self):
        return self.master if self.participant_role == "master" else self.client

    def __str__(self):
        return f"{self.get_participant_role_display()} support #{self.id}"


class SupportMessage(TimeStampedUUIDModel):
    ROLE_CHOICES = (("client", "Client"), ("master", "Master"), ("admin", "Admin"))
    chat = models.ForeignKey(
        SupportChat,
        on_delete=models.CASCADE,
        related_name="messages",
        null=True,
        blank=True,
    )
    sender_role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, null=True, blank=True)
    master = models.ForeignKey("accounts.Master", on_delete=models.CASCADE, null=True, blank=True)
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_messages",
    )
    message = models.TextField()
    attachment = models.FileField(upload_to="support/", null=True, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ("created_at",)
