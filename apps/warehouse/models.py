from django.db import models

from apps.common.models import TimeStampedUUIDModel


class WarehouseCategory(TimeStampedUUIDModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "Warehouse category"
        verbose_name_plural = "Warehouse categories"

    def __str__(self):
        return self.name


class WarehouseProduct(TimeStampedUUIDModel):
    category = models.ForeignKey(
        WarehouseCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name="products"
    )
    name = models.CharField(max_length=180)
    unit = models.CharField(max_length=20, default="dona")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    low_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sale_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    image = models.ImageField(upload_to="warehouse/products/", null=True, blank=True)
    is_active = models.BooleanField(default=True)

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_threshold

    @property
    def stock_value(self):
        """Tannarx bo'yicha ombordagi qoldiq qiymati (Ombor qiymati kartasi uchun)."""
        return self.cost_price * self.quantity

    def __str__(self):
        return self.name


class StockMovement(TimeStampedUUIDModel):
    IN = "kirim"
    OUT = "chiqim"
    TYPES = ((IN, "Kirim"), (OUT, "Chiqim"))

    product = models.ForeignKey(WarehouseProduct, on_delete=models.CASCADE, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=TYPES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    master = models.ForeignKey("accounts.Master", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


class MasterInventory(TimeStampedUUIDModel):
    master = models.ForeignKey("accounts.Master", on_delete=models.CASCADE, related_name="inventory")
    warehouse_product = models.ForeignKey(WarehouseProduct, on_delete=models.PROTECT, related_name="master_items")
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=20, default="dona")
    low_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    image = models.ImageField(upload_to="masters/inventory/", null=True, blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("master", "warehouse_product")
        ordering = ("warehouse_product__name",)

    @property
    def is_low_stock(self):
        return self.quantity <= self.low_threshold

    def __str__(self):
        return f"{self.master} - {self.warehouse_product}"
