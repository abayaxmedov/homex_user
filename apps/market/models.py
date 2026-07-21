from django.db import models

from apps.common.models import TimeStampedUUIDModel


class MarketCategory(TimeStampedUUIDModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)

    def __str__(self):
        return self.name


class MarketProduct(TimeStampedUUIDModel):
    NEW = "new"
    USED = "used"
    CONDITIONS = ((NEW, "Yangi"), (USED, "Ishlatilgan"))

    category = models.ForeignKey(MarketCategory, on_delete=models.SET_NULL, null=True, blank=True)
    seller = models.ForeignKey("accounts.Client", on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    condition = models.CharField(max_length=20, choices=CONDITIONS, default=NEW)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    is_moderated = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.name


class MarketProductImage(TimeStampedUUIDModel):
    product = models.ForeignKey(MarketProduct, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="market/products/")


class MarketFavorite(TimeStampedUUIDModel):
    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, related_name="market_favorites")
    product = models.ForeignKey(MarketProduct, on_delete=models.CASCADE, related_name="favorited_by")

    class Meta:
        unique_together = ("client", "product")


class MarketOrder(TimeStampedUUIDModel):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    STATUSES = ((PENDING, "Pending"), (CONFIRMED, "Confirmed"), (DELIVERED, "Delivered"), (CANCELLED, "Cancelled"))

    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, related_name="market_orders")
    product = models.ForeignKey(MarketProduct, on_delete=models.PROTECT, related_name="orders")
    quantity = models.PositiveIntegerField()
    delivery_address = models.CharField(max_length=300)
    phone = models.CharField(max_length=20)
    note = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUSES, default=PENDING)

    def save(self, *args, **kwargs):
        # Snapshot the price at purchase time only — never re-price a historical order
        # on later edits (e.g. an admin status change) from the current product price.
        if self._state.adding:
            self.total_amount = self.product.price * self.quantity
        super().save(*args, **kwargs)
