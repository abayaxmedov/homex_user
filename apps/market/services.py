from django.db import transaction
from rest_framework import serializers

from apps.market.models import MarketOrder, MarketProduct


@transaction.atomic
def place_market_order(*, client, product, quantity, **fields):
    """Create a market order and decrement the product's stock atomically.

    Single path for both the client and dashboard order-create flows. Locks the
    product row, rejects an unavailable product or oversell, and reserves the stock
    so the marketplace can't sell more than it has.
    """
    product = MarketProduct.objects.select_for_update().get(pk=product.pk)
    if not (product.is_active and product.is_moderated):
        raise serializers.ValidationError({"product": "Mahsulot mavjud emas"})
    if quantity > product.quantity:
        raise serializers.ValidationError({"quantity": "Omborda yetarli mahsulot yo'q"})
    product.quantity -= quantity
    product.save(update_fields=["quantity", "updated_at"])
    return MarketOrder.objects.create(client=client, product=product, quantity=quantity, **fields)
