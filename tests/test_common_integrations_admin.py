from django.contrib import admin
from django.urls import reverse

from apps.accounts.models import Client, Master
from apps.integrations.adapters import MapsClient, PaymentClient, PushClient, SMSClient
from apps.market.models import MarketCategory
from apps.notifications.models import Notification
from apps.orders.models import Order, Review
from apps.profiles.models import ClientAddress, PrivacyPolicy, Tariff, TariffFeature
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


def test_sms_client_eskiz_sends_template_and_caches_token(settings, monkeypatch):
    from django.core.cache import cache

    settings.SMS_PROVIDER = "eskiz"
    settings.SMS_EMAIL = "a@b.uz"
    settings.SMS_PASSWORD = "secret"
    settings.SMS_FROM = "4546"
    cache.delete("eskiz:sms:token")

    calls = []

    class FakeResp:
        status_code = 200

        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

        def raise_for_status(self):
            pass

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        if url.endswith("/auth/login"):
            return FakeResp({"data": {"token": "TKN"}})
        return FakeResp({"id": "1", "status": "waiting"})

    monkeypatch.setattr("apps.integrations.adapters.requests.post", fake_post)

    result = SMSClient().send_otp("+998901234567", "123456")

    assert result.ok is True and result.provider == "eskiz"
    login, send = calls[0], calls[1]
    assert login["url"].endswith("/auth/login")
    assert send["url"].endswith("/message/sms/send")
    assert send["json"]["mobile_phone"] == "998901234567"  # '+' stripped for Eskiz
    assert send["json"]["from"] == "4546"
    assert send["json"]["message"] == (
        "Kodni hech kimga bermang! HomeX ilovasiga kirish uchun tasdiqlash kodi: 123456"
    )
    assert send["headers"]["Authorization"] == "Bearer TKN"

    # A second send reuses the cached token (no second /auth/login round-trip).
    calls.clear()
    SMSClient().send_otp("+998901234567", "654321")
    assert not any(c["url"].endswith("/auth/login") for c in calls)


def test_sms_provider_check_flags_eskiz_without_creds(settings):
    from apps.integrations.checks import sms_provider_configured

    settings.SMS_PROVIDER = "eskiz"
    settings.SMS_EMAIL = ""
    settings.SMS_PASSWORD = ""
    settings.SMS_FROM = "4546"
    errors = sms_provider_configured(None)
    assert any(e.id == "integrations.E001" for e in errors)  # boot-time fail-fast

    # Fully configured -> no error.
    settings.SMS_EMAIL = "a@b.uz"
    settings.SMS_PASSWORD = "secret"
    assert sms_provider_configured(None) == []


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
        TariffFeature,
        PrivacyPolicy,
        Notification,
        SupportMessage,
    }

    assert expected.issubset(set(admin.site._registry))
