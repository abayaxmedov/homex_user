from datetime import date, time

from django.urls import reverse

from apps.orders.models import Order
from apps.profiles.models import ClientAddress, ClientDevice, MasterCertificate, MasterDocument, PrivacyPolicy, Tariff


def test_client_services_are_grouped_with_prices(client_api, service):
    response = client_api.get(reverse("client-services"))

    assert response.status_code == 200
    assert response.data["success"] is True
    assert response.data["data"][0]["services"][0]["prices"][0]["title"] == "Standart"


def test_client_address_crud_is_scoped_to_user(client_api, client_user):
    create = client_api.post(
        reverse("client-addresses"),
        {
            "label": "Uy",
            "address_text": "Yunusobod",
            "lat": "41.30000000",
            "lng": "69.25000000",
            "is_default": True,
        },
        format="json",
    )

    assert create.status_code == 201
    address = ClientAddress.objects.get(client=client_user)
    detail = client_api.get(reverse("client-address-detail", args=[address.id]))
    assert detail.status_code == 200
    assert detail.data["data"]["label"] == "Uy"


def test_client_device_crud_and_order_hint(client_api, client_user, service):
    address = ClientAddress.objects.create(
        client=client_user,
        label="Ofis",
        address_text="Uchtepa",
        lat="41.30000000",
        lng="69.25000000",
    )
    response = client_api.post(
        reverse("client-devices"),
        {
            "name": "Samsung AR12",
            "category": str(service.category_id),
            "model": "AR12",
            "address": str(address.id),
            "status": "active",
        },
        format="json",
    )

    assert response.status_code == 201
    device = ClientDevice.objects.get(client=client_user)
    order_hint = client_api.post(reverse("client-device-order", args=[device.id]))
    assert order_hint.status_code == 200
    assert str(order_hint.data["data"]["device_id"]) == str(device.id)


def test_tariff_subscription_updates_client(client_api, client_user):
    tariff = Tariff.objects.create(name="Premium", price=50000, duration_days=30)

    response = client_api.post(reverse("client-tariff-subscribe"), {"tariff_id": str(tariff.id)}, format="json")

    assert response.status_code == 200
    client_user.refresh_from_db()
    assert client_user.current_tariff == tariff
    assert client_user.tariff_expires_at is not None


def test_client_profile_returns_tariff_name_and_address_count(client_api, client_user):
    tariff = Tariff.objects.create(name="Premium", price=50000, duration_days=30)
    client_user.current_tariff = tariff
    client_user.save(update_fields=["current_tariff"])
    ClientAddress.objects.create(
        client=client_user,
        label="Uy",
        address_text="Chilonzor",
        lat="41.30000000",
        lng="69.25000000",
    )
    ClientAddress.objects.create(
        client=client_user,
        label="Ish",
        address_text="Yunusobod",
        lat="41.33000000",
        lng="69.28000000",
    )

    response = client_api.get(reverse("client-profile"))

    assert response.status_code == 200
    assert response.data["data"]["current_tariff"] == "Premium"
    assert response.data["data"]["addresses_count"] == 2


def test_master_documents_and_privacy_policy(master_api, master):
    certificate = MasterCertificate.objects.create(master=master, title="HVAC", file="certificates/hvac.pdf")
    document = MasterDocument.objects.create(master=master, title="Passport", file="documents/passport.pdf")
    PrivacyPolicy.objects.create(content="<p>Policy</p>", version="1.0")

    certs = master_api.get(reverse("master-certificates"))
    docs = master_api.get(reverse("master-documents"))
    privacy = master_api.get(reverse("privacy-policy"))

    assert certs.status_code == 200
    assert docs.status_code == 200
    assert privacy.status_code == 200
    assert str(certificate.id) in {row["id"] for row in certs.data["results"]}
    assert str(document.id) in {row["id"] for row in docs.data["results"]}
    assert privacy.data["data"]["version"] == "1.0"
