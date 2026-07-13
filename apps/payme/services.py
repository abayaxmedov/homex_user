"""Business logic that binds Payme to HomeX orders.

Kept separate from the webhook view so the state machine stays thin and the
HomeX-specific parts (amount, fulfilment, fiscal detail) live in one place.
"""
import logging
from decimal import Decimal

from django.utils import timezone

from apps.payme.types.response.webhook import Item

logger = logging.getLogger(__name__)

TIYIN = Decimal("100")


def to_tiyin(amount) -> int:
    """Convert a so'm amount (Decimal/number) to integer tiyin (1 so'm = 100)."""
    return int((Decimal(amount) * TIYIN).to_integral_value())


def order_amount_tiyin(order) -> int:
    """The order's payable total in tiyin (the value Payme must send)."""
    return to_tiyin(order.total_amount)


# ---------------------------------------------------------------------------
# Fulfilment side-effects (idempotent — safe to call more than once)
# ---------------------------------------------------------------------------

def mark_order_paid(order) -> None:
    """Mark the order paid on a successful PerformTransaction. Idempotent."""
    if order.is_paid:
        return
    order.is_paid = True
    order.paid_at = timezone.now()
    order.save(update_fields=["is_paid", "paid_at", "updated_at"])
    logger.info("Payme: order %s marked paid", order.id)


def mark_order_payment_cancelled(order) -> None:
    """Revert the paid flag on a CancelTransaction (incl. post-perform refund).

    Only the payment flag is touched — the order's fulfilment ``status`` lifecycle
    is intentionally left alone (payment and fulfilment are orthogonal in HomeX).
    """
    if not order.is_paid:
        return
    order.is_paid = False
    order.save(update_fields=["is_paid", "updated_at"])
    logger.info("Payme: order %s payment cancelled", order.id)


# ---------------------------------------------------------------------------
# Fiscal detail builder
# ---------------------------------------------------------------------------

def build_fiscal_items(order):
    """Build the fiscal ``detail.items`` for an order.

    Guarantees ``sum(price * count) == order_amount_tiyin(order)`` so Payme
    accepts the receipt. Returns ``[]`` (allow-only, no fiscal detail) when the
    receipt cannot be built correctly — a missing MXIK code on any line, or a
    total that cannot be reconciled (e.g. bonus exceeds the service fee). Those
    cases are logged for follow-up rather than sent with wrong fiscal data.
    """
    service = order.service
    service_code = getattr(service, "mxik", "") or ""
    if not service_code:
        logger.warning("Payme: order %s service has no MXIK code; skipping fiscal detail", order.id)
        return []

    target = order_amount_tiyin(order)
    items = []
    inventory_sum = 0

    usages = order.inventory_usages.select_related("inventory__warehouse_product").all()
    for usage in usages:
        product = usage.inventory.warehouse_product
        code = getattr(product, "mxik", "") or ""
        if not code:
            logger.warning(
                "Payme: order %s product %s has no MXIK code; skipping fiscal detail",
                order.id,
                product.id,
            )
            return []

        quantity = usage.quantity
        if quantity > 0 and quantity == quantity.to_integral_value():
            count = int(quantity)
            price = to_tiyin(usage.unit_price)
        else:
            # Fractional/zero quantity: fall back to a single line at the line total.
            count = 1
            price = to_tiyin(usage.total_price)

        inventory_sum += price * count
        items.append(
            Item(
                title=product.name,
                price=price,
                count=count,
                code=code,
                vat_percent=getattr(product, "vat_percent", 0) or 0,
                package_code=getattr(product, "package_code", "") or "",
            )
        )

    # The service line balances the receipt so the items sum equals the charged
    # amount (this is where a bonus/discount on the service fee lands).
    service_price = target - inventory_sum
    if service_price < 0:
        logger.warning(
            "Payme: order %s items exceed total (bonus > service fee?); skipping fiscal detail",
            order.id,
        )
        return []

    items.insert(
        0,
        Item(
            title=service.name,
            price=service_price,
            count=1,
            code=service_code,
            vat_percent=getattr(service, "vat_percent", 0) or 0,
            package_code=getattr(service, "package_code", "") or "",
        ),
    )

    if sum(item.price * item.count for item in items) != target:
        logger.warning("Payme: order %s fiscal items do not sum to amount; skipping", order.id)
        return []

    return items
