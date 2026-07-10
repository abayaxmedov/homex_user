from django.db import models

from apps.common.models import TimeStampedUUIDModel


class MasterWallet(TimeStampedUUIDModel):
    master = models.OneToOneField("accounts.Master", on_delete=models.CASCADE, related_name="wallet")
    balance_online = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance_cash = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    @property
    def total_balance(self):
        """Umumiy (spendable) balans = naqd + online. Alohida stored maydon yo'q,
        shuning uchun naqd yechilganda (balance_cash kamayganda) bu ham kamayadi."""
        return self.balance_cash + self.balance_online

    def __str__(self):
        return f"{self.master} wallet"


class WalletTransaction(TimeStampedUUIDModel):
    IN = "kirim"
    OUT = "chiqim"
    TYPES = ((IN, "Kirim"), (OUT, "Chiqim"))
    ONLINE = "online"
    CASH = "cash"
    PAYMENT_METHODS = ((ONLINE, "Online"), (CASH, "Naqd"))

    master = models.ForeignKey("accounts.Master", on_delete=models.CASCADE, related_name="wallet_transactions")
    transaction_type = models.CharField(max_length=20, choices=TYPES)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=200)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


class WithdrawRequest(TimeStampedUUIDModel):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUSES = ((PENDING, "Pending"), (APPROVED, "Approved"), (REJECTED, "Rejected"))

    master = models.ForeignKey("accounts.Master", on_delete=models.CASCADE, related_name="withdraw_requests")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUSES, default=PENDING)
    admin_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=0), name="withdraw_request_amount_positive"),
        ]


class CashHandover(WithdrawRequest):
    """Proxy of :class:`WithdrawRequest` for the admin "accept cash from master" queue."""

    class Meta:
        proxy = True
        verbose_name = "Masterdan naqd pul"
        verbose_name_plural = "Masterdan naqd pul qabul qilish"


class MasterExpense(TimeStampedUUIDModel):
    master = models.ForeignKey("accounts.Master", on_delete=models.CASCADE, related_name="expenses")
    purpose = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    product_name = models.CharField(max_length=160, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    quantity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-date", "-created_at")
