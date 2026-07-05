import uuid

from django.db import models

from apps.common.models import TimeStampedUUIDModel


class OrderStatus(models.TextChoices):
    NEW = "new", "New"
    ACCEPTED = "accepted", "Accepted"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    REJECTED = "rejected", "Rejected"


class PaymentType(models.TextChoices):
    CASH = "cash", "Naqd"
    ONLINE = "online", "Online"
    CARD = "card", "Karta"
    PLASTIC = "plastic", "Plastik"


class HomeBanner(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    banner_url = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.banner_url or str(self.id)

    def as_home_payload(self, request=None):
        banner_url = self.banner_url or None
        if banner_url and banner_url.startswith("/") and request is not None:
            banner_url = request.build_absolute_uri(banner_url)

        return {
            "id": str(self.id),
            "banner_url": banner_url,
            "is_active": self.is_active,
        }


class Order(TimeStampedUUIDModel):
    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, related_name="orders")
    master = models.ForeignKey(
        "accounts.Master", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    service = models.ForeignKey("services.Service", on_delete=models.PROTECT, related_name="orders")
    address = models.ForeignKey(
        "profiles.ClientAddress", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    device = models.ForeignKey(
        "profiles.ClientDevice", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    address_text = models.CharField(max_length=300)
    lat = models.DecimalField(max_digits=10, decimal_places=8)
    lng = models.DecimalField(max_digits=11, decimal_places=8)
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    note = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=OrderStatus.choices, default=OrderStatus.NEW)
    payment_type = models.CharField(max_length=20, choices=PaymentType.choices, default=PaymentType.CASH)
    service_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    inventory_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus_used = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    before_photo = models.ImageField(upload_to="orders/before/", null=True, blank=True)
    completion_photo = models.ImageField(upload_to="orders/completions/", null=True, blank=True)
    receipt_approved_at = models.DateTimeField(null=True, blank=True)
    receipt_approved_by = models.ForeignKey(
        "accounts.Master",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_order_receipts",
    )
    cancel_reason = models.CharField(max_length=255, blank=True)
    rejected_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at",)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        # Remember the status as loaded so post_save can detect transitions
        # and broadcast them to the client's tracking socket.
        instance._loaded_status = instance.status
        return instance

    def recalculate_total(self):
        self.total_amount = max(self.service_fee + self.inventory_total - self.bonus_used, 0)

    def __str__(self):
        return f"{self.service} - {self.status}"


class OrderInventoryUsage(TimeStampedUUIDModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="inventory_usages")
    inventory = models.ForeignKey("warehouse.MasterInventory", on_delete=models.PROTECT, related_name="order_usages")
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class OrderTracking(TimeStampedUUIDModel):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="tracking")
    master_lat = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    master_lng = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    eta_minutes = models.PositiveIntegerField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self):
        return f"{self.order_id} tracking"


class Review(TimeStampedUUIDModel):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="review")
    master = models.ForeignKey("accounts.Master", on_delete=models.CASCADE, related_name="reviews")
    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True)
    is_official = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.master} - {self.rating}"


class ReviewPhoto(TimeStampedUUIDModel):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="reviews/")
