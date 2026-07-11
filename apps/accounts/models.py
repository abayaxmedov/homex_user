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
    fcm_token = models.CharField(max_length=512, blank=True)
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
    is_blocked = models.BooleanField(default=False)
    blocked_at = models.DateTimeField(null=True, blank=True)
    block_reason = models.CharField(max_length=255, blank=True)
    lat = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    lng = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    last_location_at = models.DateTimeField(null=True, blank=True)
    language = models.CharField(max_length=5, choices=Language.choices, default=Language.UZ)
    notifications_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=True)
    fcm_token = models.CharField(max_length=512, blank=True)
    is_active = models.BooleanField(default=True)

    @property
    def is_authenticated(self):
        return True

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._loaded_status_fields = instance.status_fields()
        return instance

    @property
    def role(self):
        return "master"

    def status_fields(self):
        return (
            self.is_active,
            self.is_online,
            self.is_available,
            self.is_blocked,
            self.approval_status,
        )

    @property
    def is_approved(self):
        return self.approval_status == MasterApprovalStatus.APPROVED

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def block(self, reason=""):
        from django.utils import timezone

        self.is_blocked = True
        self.is_active = False
        self.is_available = False
        self.is_online = False
        self.block_reason = reason or ""
        self.blocked_at = timezone.now()

    def unblock(self):
        self.is_blocked = False
        self.is_active = True
        self.block_reason = ""
        self.blocked_at = None

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


class MasterApplication(Master):
    """Proxy of :class:`Master` for pending (non-active) registration applications.

    Registered as a separate admin entry so masters who left a registration
    application (``approval_status=pending``) can be reviewed apart from the
    active roster.
    """

    class Meta:
        proxy = True
        verbose_name = "Ariza qoldirgan usta"
        verbose_name_plural = "Ariza qoldirgan ustalar"


class BlockedMaster(Master):
    """Proxy of :class:`Master` limited to blocked masters (``is_blocked=True``)."""

    class Meta:
        proxy = True
        verbose_name = "Bloklangan usta"
        verbose_name_plural = "Bloklangan ustalar"


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
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.role}:{self.platform or 'unknown'}"
