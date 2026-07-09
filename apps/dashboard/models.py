from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedUUIDModel


class DashboardStaffProfile(TimeStampedUUIDModel):
    ADMIN = "admin"
    OPERATOR = "operator"
    WAREHOUSE = "warehouse"
    FINANCE = "finance"
    SUPPORT = "support"
    ROLES = (
        (ADMIN, "Admin"),
        (OPERATOR, "Operator"),
        (WAREHOUSE, "Omborchi"),
        (FINANCE, "Moliyachi"),
        (SUPPORT, "Support"),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dashboard_profile")
    role = models.CharField(max_length=30, choices=ROLES, default=OPERATOR)
    phone = models.CharField(max_length=20, blank=True)
    permissions = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ("user__username",)

    def __str__(self):
        return f"{self.user} - {self.role}"


class DashboardOrderAssistant(TimeStampedUUIDModel):
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="dashboard_assistants")
    assistant = models.ForeignKey("accounts.Master", on_delete=models.PROTECT, related_name="assistant_orders")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_dashboard_assistants",
    )
    note = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)
        unique_together = ("order", "assistant")

    def __str__(self):
        return f"{self.order_id} - {self.assistant}"


class DashboardLiveStream(TimeStampedUUIDModel):
    LIVE = "live"
    ARCHIVED = "archived"
    ENDED = "ended"
    OFFLINE = "offline"
    STATUSES = (
        (LIVE, "Jonli efir"),
        (ARCHIVED, "Arxiv"),
        (ENDED, "Yakunlangan"),
        (OFFLINE, "Offline"),
    )

    title = models.CharField(max_length=180)
    service_name = models.CharField(max_length=160, blank=True)
    master = models.ForeignKey("accounts.Master", on_delete=models.SET_NULL, null=True, blank=True)
    client = models.ForeignKey("accounts.Client", on_delete=models.SET_NULL, null=True, blank=True)
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True)
    stream_url = models.URLField(blank=True)
    archive_url = models.URLField(blank=True)
    thumbnail = models.ImageField(upload_to="dashboard/live-streams/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUSES, default=LIVE)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title


class DashboardCompanyExpense(TimeStampedUUIDModel):
    purpose = models.CharField(max_length=120)
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("-date", "-created_at")

    def __str__(self):
        return self.name


class DashboardWarehouseExpense(TimeStampedUUIDModel):
    product = models.ForeignKey("warehouse.WarehouseProduct", on_delete=models.SET_NULL, null=True, blank=True)
    purpose = models.CharField(max_length=120)
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("-date", "-created_at")

    def __str__(self):
        return self.name


class DashboardIntegrationSetting(TimeStampedUUIDModel):
    key = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=160)
    value = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("key",)

    def __str__(self):
        return self.title


class DashboardBackup(TimeStampedUUIDModel):
    """A full database dump (.sql) stored under ``settings.BACKUP_ROOT``.

    The file itself lives on disk (private, not in MEDIA); this row holds the
    metadata and is what the download endpoint resolves.
    """

    MANUAL = "manual"
    AUTO = "auto"
    SOURCES = ((MANUAL, "Qo'lda"), (AUTO, "Avtomatik"))

    filename = models.CharField(max_length=255, unique=True)
    size_bytes = models.BigIntegerField(default=0)
    engine = models.CharField(max_length=40, blank=True, help_text="postgresql / sqlite")
    source = models.CharField(max_length=10, choices=SOURCES, default=MANUAL)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.filename

    @property
    def path(self):
        from django.conf import settings as dj_settings

        return dj_settings.BACKUP_ROOT / self.filename

    @property
    def exists(self):
        return self.path.exists()
