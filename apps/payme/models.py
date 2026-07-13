"""Payme transaction model.

Tracks every Payme (Paycom) transaction and its state over time. The state
machine mirrors the Merchant API protocol:

    1  (INITIATING)            — created, awaiting perform
    2  (SUCCESSFULLY)          — performed / paid
    -1 (CANCELED_DURING_INIT)  — cancelled before perform
    -2 (CANCELED)              — cancelled / refunded after perform
"""
from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedUUIDModel


class PaymeTransaction(TimeStampedUUIDModel):
    CREATED = 0
    INITIATING = 1
    SUCCESSFULLY = 2
    CANCELED = -2
    CANCELED_DURING_INIT = -1

    STATE = [
        (CREATED, "Created"),
        (INITIATING, "Initiating"),
        (SUCCESSFULLY, "Performed"),
        (CANCELED, "Cancelled after perform"),
        (CANCELED_DURING_INIT, "Cancelled during initiation"),
    ]

    transaction_id = models.CharField(max_length=64, unique=True)
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, related_name="payme_transactions"
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # stored in tiyin
    state = models.IntegerField(choices=STATE, default=CREATED)
    fiscal_data = models.JSONField(default=dict, blank=True)
    cancel_reason = models.IntegerField(null=True, blank=True)
    performed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    cancelled_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "Payme Transaction"
        verbose_name_plural = "Payme Transactions"
        ordering = ("-created_at",)
        db_table = "payme_transactions"
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["order", "state"]),
        ]

    def __str__(self):
        return f"Payme #{self.transaction_id} order={self.order_id} state={self.state}"

    @classmethod
    def get_by_transaction_id(cls, transaction_id):
        """Fetch a transaction by its Payme id or raise ``TransactionNotFound``."""
        from apps.payme import exceptions

        try:
            return cls.objects.get(transaction_id=transaction_id)
        except cls.DoesNotExist as exc:
            raise exceptions.TransactionNotFound(str(transaction_id)) from exc

    def is_performed(self) -> bool:
        return self.state == self.SUCCESSFULLY

    def is_cancelled(self) -> bool:
        return self.state in (self.CANCELED, self.CANCELED_DURING_INIT)

    def is_created(self) -> bool:
        return self.state == self.CREATED

    def is_initiating(self) -> bool:
        """A state-1 transaction created in Payme, awaiting perform."""
        return self.state == self.INITIATING

    def mark_as_cancelled(self, cancel_reason, state) -> "PaymeTransaction":
        """Idempotently move the transaction into a cancelled state."""
        if self.state == state:
            return self

        self.state = state
        self.cancel_reason = cancel_reason
        self.cancelled_at = timezone.now()
        self.save(update_fields=["state", "cancel_reason", "cancelled_at", "updated_at"])
        return self

    def mark_as_performed(self) -> bool:
        """Move an initiating transaction to performed. Returns success."""
        if self.state != self.INITIATING:
            return False

        self.state = self.SUCCESSFULLY
        self.performed_at = timezone.now()
        self.save(update_fields=["state", "performed_at", "updated_at"])
        return True
