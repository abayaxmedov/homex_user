from django.db import models

from apps.common.models import TimeStampedUUIDModel


class ServiceCategory(TimeStampedUUIDModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    icon = models.ImageField(upload_to="services/icons/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class Service(TimeStampedUUIDModel):
    category = models.ForeignKey(ServiceCategory, on_delete=models.CASCADE, related_name="services")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("category__sort_order", "name")

    def __str__(self):
        return self.name


class ServicePrice(TimeStampedUUIDModel):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="prices")
    title = models.CharField(max_length=160)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=40, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.service} - {self.title}"
