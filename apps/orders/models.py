import uuid

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedUUIDModel


class OrderStatus(models.TextChoices):
    NEW = "new", "Yangi"
    ACCEPTED = "accepted", "Qabul qilindi"
    ON_WAY = "on_way", "Yo'lda"
    ARRIVED = "arrived", "Yetib keldi"
    COMPLETED = "completed", "Yakunlandi"
    CANCELLED = "cancelled", "Bekor qilindi"
    REJECTED = "rejected", "Rad etildi"


# Statuses in which a master is actively handling the order (lead master set).
ACTIVE_ORDER_STATUSES = (OrderStatus.ACCEPTED, OrderStatus.ON_WAY, OrderStatus.ARRIVED)

# Terminal statuses — an order here has already run (or forfeited) its side effects.
TERMINAL_ORDER_STATUSES = (OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REJECTED)


def can_admin_set_status(current, new):
    """Whether an admin/generic write serializer may move an order `current` -> `new`.

    Completing an order must run the master completion flow (OrderCompleteSerializer:
    it credits the wallet, deducts inventory and approves the receipt). So a generic
    status write may NOT set ``completed`` and may NOT revive a terminal order — both
    would leave money/stock inconsistent. A no-op (same status) is always allowed.
    """
    if current == new:
        return True
    if new == OrderStatus.COMPLETED:
        return False
    if current in TERMINAL_ORDER_STATUSES:
        return False
    return True

# Maps the fine-grained order status to the coarse dashboard tab/badge bucket
# used in the Figma design (Yangi / Yo'lda / Bajarilmoqda / Yakunlangan / Bekor).
STATUS_TAB = {
    OrderStatus.NEW: "yangi",
    OrderStatus.ACCEPTED: "bajarilmoqda",
    OrderStatus.ON_WAY: "yo'lda",
    OrderStatus.ARRIVED: "bajarilmoqda",
    OrderStatus.COMPLETED: "yakunlangan",
    OrderStatus.CANCELLED: "bekor",
    OrderStatus.REJECTED: "bekor",
}


class PaymentType(models.TextChoices):
    CASH = "cash", "Naqd"
    ONLINE = "online", "Online"
    CARD = "card", "Karta"
    PLASTIC = "plastic", "Plastik"


class HomeBanner(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    banner_image = models.ImageField(upload_to="home/banners/", null=True, blank=True)
    banner_url = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.banner_url or (self.banner_image.name if self.banner_image else str(self.id))

    def as_home_payload(self, request=None):
        banner_image = self.banner_image.url if self.banner_image else None
        if banner_image and request is not None:
            banner_image = request.build_absolute_uri(banner_image)

        banner_url = self.banner_url or None
        if banner_url and banner_url.startswith("/") and request is not None:
            banner_url = request.build_absolute_uri(banner_url)
        if not banner_url:
            banner_url = banner_image

        return {
            "id": str(self.id),
            "banner_image": banner_image,
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
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
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
        # and broadcast realtime updates.
        instance._loaded_status = instance.status
        instance._loaded_master_id = instance.master_id
        return instance

    def recalculate_total(self):
        self.total_amount = max(self.service_fee + self.inventory_total - self.bonus_used, 0)

    def __str__(self):
        return f"{self.service} - {self.status}"


class OrderMaster(TimeStampedUUIDModel):
    """A master the admin assigned to an order (dashboard "Usta biriktirish").

    An order can have several assigned masters; ``Order.master`` records the one
    who first accepts and becomes the lead (used for tracking / lifecycle).
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="assigned_masters")
    master = models.ForeignKey("accounts.Master", on_delete=models.PROTECT, related_name="assigned_orders")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # dashboard admin who assigned the master
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_order_masters",
    )
    has_accepted = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("created_at",)
        unique_together = ("order", "master")

    def __str__(self):
        return f"{self.order_id} - {self.master}"


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
