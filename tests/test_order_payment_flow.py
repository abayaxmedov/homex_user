from datetime import date, time
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import MasterLevel
from apps.orders.models import Order, OrderStatus
from apps.payme.services import mark_order_paid
from apps.profiles.models import ClientAddress, ClientDevice
from apps.wallet.models import MasterWallet, WalletTransaction


def _order(client_user, service, master=None, status=OrderStatus.NEW, **extra):
    return Order.objects.create(
        client=client_user,
        master=master,
        service=service,
        address_text="Tashkent",
        lat="41.30000000",
        lng="69.25000000",
        scheduled_date=date.today(),
        scheduled_time=time(10, 0),
        status=status,
        **extra,
    )


def test_order_create_has_no_payment_type_or_service_fee(client_api, service):
    resp = client_api.post(
        reverse("client-orders"),
        {
            "service": str(service.id),
            "address_text": "Chilonzor",
            "lat": "41.30000000",
            "lng": "69.25000000",
            "scheduled_date": date.today().isoformat(),
            "scheduled_time": "10:00:00",
        },
        format="json",
    )
    assert resp.status_code == 201
    order = Order.objects.get(id=resp.data["data"]["id"])
    assert order.payment_type in (None, "")  # not chosen at creation
    assert order.service_fee == 0  # not taken from the service catalog
    assert order.total_amount == 0


def test_client_can_download_check_at_awaiting_payment(client_api, client_user, service, master):
    order = _order(
        client_user,
        service,
        master=master,
        status=OrderStatus.AWAITING_PAYMENT,
        service_fee=Decimal("150000"),
        total_amount=Decimal("150000"),
        receipt_approved_at=timezone.now(),
    )
    resp = client_api.get(reverse("client-order-receipt-download", args=[order.id]))
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"


def test_online_payment_completes_awaiting_order_and_credits_master(client_user, service, master):
    order = _order(
        client_user,
        service,
        master=master,
        status=OrderStatus.AWAITING_PAYMENT,
        service_fee=Decimal("200000"),
        total_amount=Decimal("200000"),
    )
    # Payme PerformTransaction -> mark_order_paid -> completes + credits (online).
    mark_order_paid(order)
    order.refresh_from_db()

    assert order.status == OrderStatus.COMPLETED
    assert order.is_paid is True
    wallet = MasterWallet.objects.get(master=master)
    assert wallet.balance_online == Decimal("200000")
    assert WalletTransaction.objects.filter(
        master=master,
        transaction_type=WalletTransaction.IN,
        payment_method=WalletTransaction.ONLINE,
        amount=Decimal("200000"),
    ).exists()


def test_dashboard_master_edit_daraja_and_address(admin_api, master):
    resp = admin_api.patch(
        reverse("dashboard-master-detail", args=[master.id]),
        {"daraja": MasterLevel.KATTA_USTA, "address": "Yunusobod 12-uy"},
        format="json",
    )
    assert resp.status_code == 200
    master.refresh_from_db()
    assert master.daraja == MasterLevel.KATTA_USTA
    assert master.address == "Yunusobod 12-uy"


def test_awaiting_payment_stays_in_master_in_progress_tab(master_api, client_user, service, master):
    from apps.orders.models import OrderMaster

    order = _order(
        client_user, service, master=master, status=OrderStatus.AWAITING_PAYMENT,
        service_fee=Decimal("100000"), total_amount=Decimal("100000"),
    )
    OrderMaster.objects.create(order=order, master=master, is_active=True)

    # "Jarayonda" (in_process) tab includes awaiting_payment — order not closed for master.
    in_process = master_api.get(reverse("master-orders"), {"tab": "in_process"})
    assert str(order.id) in [o["id"] for o in in_process.data["results"]]

    # "Tarix" (completed) tab does NOT (client hasn't paid yet).
    completed = master_api.get(reverse("master-orders"), {"tab": "completed"})
    assert str(order.id) not in [o["id"] for o in completed.data["results"]]

    # After payment -> completed -> moves to the history tab.
    order.status = OrderStatus.COMPLETED
    order.save(update_fields=["status"])
    completed2 = master_api.get(reverse("master-orders"), {"tab": "completed"})
    assert str(order.id) in [o["id"] for o in completed2.data["results"]]


def test_awaiting_payment_tracking_shows_final_step(client_api, client_user, service, master):
    order = _order(
        client_user, service, master=master, status=OrderStatus.AWAITING_PAYMENT,
        service_fee=Decimal("100000"), total_amount=Decimal("100000"),
    )
    resp = client_api.get(reverse("client-order-track", args=[order.id]))
    data = resp.data["data"]

    # awaiting_payment sits on the single final step (completed + payment as one), not reset.
    assert data["tracking_status"] == "master_finished"
    assert data["tracking_step"] == data["tracking_total_steps"] == 5
    assert all(step["is_completed"] for step in data["tracking_steps"])


def test_master_comment_reaches_client(master_api, client_api, client_user, service, master):
    order = _order(client_user, service, master=master, status=OrderStatus.ARRIVED)

    # Master submits the check with a comment ("Xizmat haqida izoh").
    submit = master_api.post(
        reverse("master-order-complete", args=[order.id]),
        {"service_fee": "150000", "comment": "Kompressor tozalandi, freon to'ldirildi"},
        format="multipart",
    )
    assert submit.status_code == 200

    # Client sees the comment on the order detail (+ tracking).
    detail = client_api.get(reverse("client-order-detail", args=[order.id]))
    assert detail.data["data"]["completion_note"] == "Kompressor tozalandi, freon to'ldirildi"
    track = client_api.get(reverse("client-order-track", args=[order.id]))
    assert track.data["data"]["completion_note"] == "Kompressor tozalandi, freon to'ldirildi"


def test_arrived_is_pure_status_transition_no_photo(master_api, client_user, service, master):
    order = _order(client_user, service, master=master, status=OrderStatus.ON_WAY)

    # "Arrived" needs no body — before_photo is provided by the client at order creation.
    resp = master_api.post(reverse("master-order-arrived", args=[order.id]))
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.ARRIVED


def test_client_uploads_before_photo_at_order_creation(client_api, master_api, client_user, service, master):
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(buf, format="PNG")
    photo = SimpleUploadedFile("before.png", buf.getvalue(), content_type="image/png")

    create = client_api.post(
        reverse("client-orders"),
        {
            "service": str(service.id),
            "address_text": "Chilonzor",
            "lat": "41.30000000",
            "lng": "69.25000000",
            "scheduled_date": date.today().isoformat(),
            "scheduled_time": "10:00:00",
            "before_photo": photo,
        },
        format="multipart",
    )
    assert create.status_code == 201
    order = Order.objects.get(id=create.data["data"]["id"])
    assert order.before_photo  # stored on the order
    # Client sees it in the create response, and the master sees it on the order detail.
    assert create.data["data"]["before_photo"]
    order.master = master
    order.save(update_fields=["master"])
    master_detail = master_api.get(reverse("master-order-detail", args=[order.id]))
    assert master_detail.data["data"]["before_photo"]


def test_client_can_delete_own_device(client_api, client_user):
    address = ClientAddress.objects.create(
        client=client_user, label="Uy", address_text="Chilonzor", lat="41.30000000", lng="69.25000000"
    )
    device = ClientDevice.objects.create(client=client_user, name="Samsung AR12", address=address)

    resp = client_api.delete(reverse("client-device-detail", args=[device.id]))
    assert resp.status_code in (200, 204)
    assert not ClientDevice.objects.filter(id=device.id).exists()
