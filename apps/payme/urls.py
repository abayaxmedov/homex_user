from django.urls import path

from apps.payme.views import (
    PaymeCheckoutUrlView,
    PaymeOrderStatusView,
    PaymeWebHookAPIView,
)

app_name = "payme"

urlpatterns = [
    # Merchant JSON-RPC webhook — this is the URL configured in the Payme kassa.
    path("", PaymeWebHookAPIView.as_view(), name="webhook"),
    # Client-facing helpers (JWT-authenticated).
    path("checkout-url/<uuid:order_id>/", PaymeCheckoutUrlView.as_view(), name="checkout-url"),
    path("order-status/<uuid:order_id>/", PaymeOrderStatusView.as_view(), name="order-status"),
]
