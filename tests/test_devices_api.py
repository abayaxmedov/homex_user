from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.accounts.models import Client
from apps.orders.models import Order
from apps.profiles.models import ClientAddress, ClientDevice


def order_payload(service, **overrides):
    payload = {
        "service": str(service.id),
        "address_text": "Chilonzor 12",
        "lat": "41.30000000",
        "lng": "69.25000000",
        "scheduled_date": str(date.today()),
        "scheduled_time": "10:00",
        "payment_type": "cash",
    }
    payload.update(overrides)
    return payload


def png_upload(name="device.png"):
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def test_order_create_saves_inline_device(client_api, client_user, service):
    response = client_api.post(
        reverse("client-orders"),
        order_payload(
            service,
            device_name="Konditsioner LG",
            device_model="X12",
            device_location_label="Uy",
        ),
        format="json",
    )

    assert response.status_code == 201
    order = Order.objects.get(id=response.data["data"]["id"])
    assert order.device is not None
    device = order.device
    assert device.client == client_user
    assert device.name == "Konditsioner LG"
    assert device.model == "X12"
    # Device saved at an auto-created location built from the order address.
    assert device.address.label == "Uy"
    assert device.address.address_text == "Chilonzor 12"
    assert ClientAddress.objects.filter(client=client_user, label="Uy").count() == 1
    # Device now shows up in the devices section.
    listing = client_api.get(reverse("client-devices"))
    assert {row["id"] for row in listing.data["results"]} == {str(device.id)}


def test_order_create_inline_device_with_image(client_api, client_user, service):
    response = client_api.post(
        reverse("client-orders"),
        order_payload(service, device_name="Muzlatgich", device_image=png_upload()),
        format="multipart",
    )

    assert response.status_code == 201
    device = Order.objects.get(id=response.data["data"]["id"]).device
    assert device is not None
    assert device.image  # photo persisted
    assert device.image.name.endswith(".png")


def test_order_create_links_existing_device(client_api, client_user, service):
    address = ClientAddress.objects.create(
        client=client_user, label="Ish", address_text="Yunusobod", lat="41.30", lng="69.25"
    )
    device = ClientDevice.objects.create(
        client=client_user, name="Split", address=address
    )

    response = client_api.post(
        reverse("client-orders"),
        order_payload(service, device=str(device.id)),
        format="json",
    )

    assert response.status_code == 201
    order = Order.objects.get(id=response.data["data"]["id"])
    assert order.device_id == device.id
    # No duplicate device created.
    assert ClientDevice.objects.filter(client=client_user).count() == 1


def test_order_create_rejects_foreign_device(client_api, service):
    other = Client.objects.create(phone="+998900001111", first_name="Boshqa")
    other_address = ClientAddress.objects.create(
        client=other, label="Uy", address_text="X", lat="41.30", lng="69.25"
    )
    foreign_device = ClientDevice.objects.create(
        client=other, name="Chet", address=other_address
    )

    response = client_api.post(
        reverse("client-orders"),
        order_payload(service, device=str(foreign_device.id)),
        format="json",
    )

    assert response.status_code == 400
    assert not Order.objects.exists()


def test_devices_filter_by_location(client_api, client_user, service):
    home = ClientAddress.objects.create(client=client_user, label="Uy", address_text="Uy", lat="41.30", lng="69.25")
    work = ClientAddress.objects.create(client=client_user, label="Ish", address_text="Ish", lat="41.31", lng="69.26")
    home_device = ClientDevice.objects.create(client=client_user, name="Uy split", address=home)
    work_device = ClientDevice.objects.create(client=client_user, name="Ish split", address=work)

    by_id = client_api.get(reverse("client-devices"), {"address_id": str(home.id)})
    by_label = client_api.get(reverse("client-devices"), {"label": "Ish"})

    assert {row["id"] for row in by_id.data["results"]} == {str(home_device.id)}
    assert {row["id"] for row in by_label.data["results"]} == {str(work_device.id)}


def test_device_locations_endpoint(client_api, client_user, service):
    home = ClientAddress.objects.create(client=client_user, label="Uy", address_text="Uy", lat="41.30", lng="69.25")
    work = ClientAddress.objects.create(client=client_user, label="Ish", address_text="Ish", lat="41.31", lng="69.26")
    ClientDevice.objects.create(client=client_user, name="d1", address=home)
    ClientDevice.objects.create(client=client_user, name="d2", address=home)
    ClientDevice.objects.create(client=client_user, name="d3", address=work)

    response = client_api.get(reverse("client-device-locations"))

    assert response.status_code == 200
    counts = {row["label"]: row["device_count"] for row in response.data["data"]["results"]}
    assert counts == {"Uy": 2, "Ish": 1}


def test_add_device_without_category(client_api, client_user):
    # Figma "Yangi uskuna" form: name, model, image, address — no category.
    address = ClientAddress.objects.create(
        client=client_user, label="Uyim", address_text="Yunusobod", lat="41.30", lng="69.25"
    )
    response = client_api.post(
        reverse("client-devices"),
        {"name": "Samsung AR12", "model": "Inverter", "address": str(address.id)},
        format="json",
    )

    assert response.status_code == 201
    device = ClientDevice.objects.get(client=client_user, name="Samsung AR12")
    assert device.model == "Inverter"
    # status defaults + label exposed
    data = response.data["data"]
    assert data["status"] == "active"
    assert data["status_label"] == "Faol"
    assert "category" not in data


def test_xizmat_chaqirish_returns_order_prefill(client_api, client_user, service):
    address = ClientAddress.objects.create(
        client=client_user, label="Office", address_text="Uchtepa, Oasis", lat="41.31", lng="69.26"
    )
    device = ClientDevice.objects.create(
        client=client_user, name="Split", model="Inverter", address=address
    )

    response = client_api.post(reverse("client-device-order", args=[device.id]))

    assert response.status_code == 200
    prefill = response.data["data"]["prefill"]
    assert prefill["device"] == str(device.id)
    assert prefill["address"] == str(address.id)
    assert prefill["address_text"] == "Uchtepa, Oasis"
    assert response.data["data"]["device"]["name"] == "Split"


def test_device_order_count_reflects_linked_orders(client_api, client_user, service):
    address = ClientAddress.objects.create(client=client_user, label="Uy", address_text="Uy", lat="41.30", lng="69.25")
    device = ClientDevice.objects.create(client=client_user, name="Split", address=address)
    for _ in range(2):
        client_api.post(reverse("client-orders"), order_payload(service, device=str(device.id)), format="json")

    listing = client_api.get(reverse("client-devices"))
    row = next(r for r in listing.data["results"] if r["id"] == str(device.id))

    assert row["order_count"] == 2
    assert row["last_order"] is not None
