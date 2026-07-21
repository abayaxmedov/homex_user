from datetime import time

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Master
from apps.orders.models import Order, OrderMaster, OrderStatus
from apps.wallet.models import WalletTransaction


def make_order(client, service, status=OrderStatus.NEW, master=None, **extra):
    return Order.objects.create(
        client=client,
        master=master,
        service=service,
        address_text="Toshkent",
        lat="41.31000000",
        lng="69.24000000",
        scheduled_date=timezone.localdate(),
        scheduled_time=time(10, 0),
        status=status,
        **extra,
    )


# --- A1: client cancel guard ---

def test_client_cannot_cancel_completed_order(client_api, client_user, service, master):
    order = make_order(client_user, service, status=OrderStatus.COMPLETED, master=master, total_amount=200000)
    resp = client_api.post(reverse("client-order-cancel", args=[order.id]), {"reason": "x"}, format="json")
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED  # unchanged


def test_client_can_cancel_active_order(client_api, client_user, service, master):
    # Contract preserved: a valid cancel still returns 200.
    order = make_order(client_user, service, status=OrderStatus.ACCEPTED, master=master)
    resp = client_api.post(reverse("client-order-cancel", args=[order.id]), {"reason": "kerak emas"}, format="json")
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED
    assert order.cancel_reason == "kerak emas"


# --- A2: master reject guard ---

def test_master_cannot_reject_completed_order(master_api, client_user, service, master):
    order = make_order(client_user, service, status=OrderStatus.COMPLETED, master=master, total_amount=200000)
    resp = master_api.post(reverse("master-order-reject", args=[order.id]), {"reason": "x"}, format="json")
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == OrderStatus.COMPLETED


# --- A3: accept race ---

def test_accept_second_master_does_not_override_lead(api_client, client_user, service, master):
    from apps.accounts.tokens import issue_role_tokens

    other = Master.objects.create(phone="+998900000077", first_name="Vali", last_name="Usta")
    order = make_order(client_user, service, status=OrderStatus.NEW)
    OrderMaster.objects.create(order=order, master=master, is_active=True)
    OrderMaster.objects.create(order=order, master=other, is_active=True)

    def as_master(m):
        c = type(api_client)()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_role_tokens(m, 'master')['access_token']}")
        return c

    r1 = as_master(master).post(reverse("master-order-accept", args=[order.id]))
    r2 = as_master(other).post(reverse("master-order-accept", args=[order.id]))
    assert r1.status_code == 200 and r2.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.ACCEPTED
    assert order.master_id == master.id  # first accepter stays lead, not overridden


# --- A4: pay guard ---

def test_client_cannot_pay_cancelled_order(client_api, client_user, service):
    order = make_order(client_user, service, status=OrderStatus.CANCELLED)
    resp = client_api.post(
        reverse("client-order-pay", args=[order.id]), {"payment_method": "online"}, format="json"
    )
    assert resp.status_code == 400


# --- B1: dashboard status endpoint blocks completed ---

def test_admin_status_completed_is_rejected(admin_api, client_user, service, master):
    order = make_order(client_user, service, status=OrderStatus.ARRIVED, master=master)
    resp = admin_api.patch(
        reverse("dashboard-order-status", args=[order.id]), {"status": "completed"}, format="json"
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == OrderStatus.ARRIVED  # not completed
    assert not WalletTransaction.objects.filter(order=order).exists()  # no payout


def test_admin_status_cancel_still_works(admin_api, client_user, service, master):
    # Contract preserved: a valid admin transition still succeeds.
    order = make_order(client_user, service, status=OrderStatus.ACCEPTED, master=master)
    resp = admin_api.patch(
        reverse("dashboard-order-status", args=[order.id]),
        {"status": "cancelled", "cancel_reason": "admin bekor"},
        format="json",
    )
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED


# --- B2: dashboard order detail blocks completed ---

def test_admin_order_detail_cannot_set_completed(admin_api, client_user, service, master):
    order = make_order(client_user, service, status=OrderStatus.ARRIVED, master=master)
    resp = admin_api.patch(
        reverse("dashboard-order-detail", args=[order.id]), {"status": "completed"}, format="json"
    )
    assert resp.status_code == 400
    order.refresh_from_db()
    assert order.status == OrderStatus.ARRIVED
