from django.contrib.auth.hashers import check_password, make_password
from django.db import models

from apps.common.models import TimeStampedUUIDModel


class Language(models.TextChoices):
    UZ = "uz", "O'zbek"
    RU = "ru", "Русский"
    EN = "en", "English"


class MasterApprovalStatus(models.TextChoices):
    PENDING = "pending", "Tasdiq kutilmoqda"
    APPROVED = "approved", "Tasdiqlangan"
    REJECTED = "rejected", "Rad etilgan"


class Client(TimeStampedUUIDModel):
    phone = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    avatar = models.ImageField(upload_to="clients/avatars/", null=True, blank=True)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.UZ)
    notifications_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=True)
    fcm_token = models.CharField(max_length=255, blank=True)
    current_tariff = models.ForeignKey(
        "profiles.Tariff", on_delete=models.SET_NULL, null=True, blank=True, related_name="clients"
    )
    tariff_expires_at = models.DateTimeField(null=True, blank=True)
    total_spent = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_orders = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    @property
    def is_authenticated(self):
        return True

    @property
    def role(self):
        return "client"

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or self.phone


class Master(TimeStampedUUIDModel):
    phone = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    password = models.CharField(max_length=128, blank=True)
    specialization = models.CharField(max_length=120, blank=True)
    avatar = models.ImageField(upload_to="masters/avatars/", null=True, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    approval_status = models.CharField(
        max_length=20,
        choices=MasterApprovalStatus.choices,
        default=MasterApprovalStatus.APPROVED,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.CharField(max_length=255, blank=True)
    is_online = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    lat = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    lng = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.UZ)
    notifications_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=True)
    fcm_token = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    @property
    def is_authenticated(self):
        return True

    @property
    def role(self):
        return "master"

    @property
    def is_approved(self):
        return self.approval_status == MasterApprovalStatus.APPROVED

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def save(self, *args, **kwargs):
        if self.password and not self.password.startswith(("pbkdf2_", "argon2$", "bcrypt")):
            self.set_password(self.password)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name or self.phone


class OTPRecord(TimeStampedUUIDModel):
    phone = models.CharField(max_length=20)
    code = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"{self.phone} - {self.created_at:%Y-%m-%d %H:%M}"


class FCMDevice(TimeStampedUUIDModel):
    ROLE_CHOICES = (("client", "Client"), ("master", "Master"))
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True, related_name="devices")
    master = models.ForeignKey(Master, on_delete=models.CASCADE, null=True, blank=True, related_name="devices")
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.role}:{self.platform or 'unknown'}"
