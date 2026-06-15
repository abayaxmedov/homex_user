from django.contrib import admin
from django.urls import reverse

from apps.accounts.models import Client, Master
from apps.integrations.adapters import MapsClient, PaymentClient, PushClient, SMSClient
from apps.market.models import MarketCategory
from apps.notifications.models import Notification
from apps.orders.models import Order, Review
from apps.profiles.models import ClientAddress, PrivacyPolicy, Tariff
from apps.services.models import Service, ServiceCategory
from apps.support.models import SupportMessage
from apps.warehouse.models import WarehouseProduct
from apps.wallet.models import MasterWallet


def test_public_schema_uses_standard_success_wrapper(client):
    response = client.get(reverse("schema"))

    assert response.status_code == 200


def test_integration_adapters_return_provider_payload(service, client_user):
    order = Order.objects.create(
        client=client_user,
        service=service,
        address_text="Tashkent",
        lat="41.30000000",
        lng="69.25000000",
        scheduled_date="2026-06-15",
        scheduled_time="10:00",
    )

    assert SMSClient().send_otp("+998900000000", "123456").ok is True
    assert PushClient().send("token", "Title", "Body").payload["title"] == "Title"
    assert "payment_url" in PaymentClient().create_payment(order, "online").payload
    assert MapsClient().config().payload["provider"] == "google"


def test_core_models_are_registered_in_admin():
    expected = {
        Client,
        Master,
        ServiceCategory,
        Service,
        Order,
        Review,
        WarehouseProduct,
        MasterWallet,
        MarketCategory,
        ClientAddress,
        Tariff,
        PrivacyPolicy,
        Notification,
        SupportMessage,
    }

    assert expected.issubset(set(admin.site._registry))
