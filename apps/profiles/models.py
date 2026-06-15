from django.db import models

from apps.common.models import TimeStampedUUIDModel


class ClientAddress(TimeStampedUUIDModel):
    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=50)
    address_text = models.CharField(max_length=300)
    lat = models.DecimalField(max_digits=10, decimal_places=8)
    lng = models.DecimalField(max_digits=11, decimal_places=8)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ("-is_default", "label")

    def __str__(self):
        return f"{self.client} - {self.label}"


class ClientDevice(TimeStampedUUIDModel):
    ACTIVE = "active"
    REPAIR = "repair"
    BROKEN = "broken"
    STATUSES = ((ACTIVE, "Faol"), (REPAIR, "Ta'mirda"), (BROKEN, "Ishlamayapti"))

    client = models.ForeignKey("accounts.Client", on_delete=models.CASCADE, related_name="client_devices")
    name = models.CharField(max_length=200)
    category = models.ForeignKey("services.ServiceCategory", on_delete=models.PROTECT)
    model = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to="clients/devices/", null=True, blank=True)
    address = models.ForeignKey(ClientAddress, on_delete=models.CASCADE, related_name="devices")
    status = models.CharField(max_length=20, choices=STATUSES, default=ACTIVE)

    def __str__(self):
        return self.name


class Tariff(TimeStampedUUIDModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    duration_days = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class MasterCertificate(TimeStampedUUIDModel):
    master = models.ForeignKey("accounts.Master", on_delete=models.CASCADE, related_name="certificates")
    title = models.CharField(max_length=160)
    file = models.FileField(upload_to="masters/certificates/")

    class Meta:
        ordering = ("-created_at",)


class MasterDocument(TimeStampedUUIDModel):
    master = models.ForeignKey("accounts.Master", on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=160)
    file = models.FileField(upload_to="masters/documents/")

    class Meta:
        ordering = ("-created_at",)


class PrivacyPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    content = models.TextField()
    version = models.CharField(max_length=20)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Privacy policies"

    def __str__(self):
        return f"Privacy policy {self.version}"
