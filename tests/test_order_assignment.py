"""Order assignment + status-flow tests for the reworked Buyurtma bo'limi.

Covers: admin assigns multiple masters/assistants (Figma "Usta/Shogird
biriktirish"), the modal "Saqlash" replaces the full set, the dashboard status
tabs (Yangi/Yo'lda/Bajarilmoqda/Yakunlangan/Bekor), and the multi-master lead
(first to accept becomes Order.master).
"""
from datetime import date, time

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import Master, MasterApprovalStatus
from apps.accounts.tokens import issue_role_tokens
from apps.orders.models import Order, OrderMaster, OrderStatus


def make_order(client_user, service, **kwargs):
    defaults = dict(
        client=client_user,
        service=service,
        address_text="Chilonzor 9",
        lat="41.30000000",
        lng="69.24000000",
        scheduled_date=date.today(),
        scheduled_time=time(10, 0),
    )
    defaults.update(kwargs)
    return Order.objects.create(**defaults)


def rows(response):
    body = response.data
    return body["results"] if "results" in body else body["data"]


@pytest.fixture
def master2(db):
    return Master.objects.create(
        phone="+998900000222",
        first_name="Ikkinchi",
        last_name="Usta",
        password="1234",
        approval_status=MasterApprovalStatus.APPROVED,
        is_active=True,
    )


@pytest.fixture
def master2_api(master2):
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_role_tokens(master2, 'master')['access_token']}")
    return api


def assign_url(order):
    return reverse("dashboard-order-assign", args=[order.id])


# --- Admin multi-assign ------------------------------------------------------

def test_dashboard_assign_multiple_masters(admin_api, master, master2, client_user, service):
    order = make_order(client_user, service)

    response = admin_api.patch(
        assign_url(order), {"masters": [str(master.id), str(master2.id)]}, format="json"
    )

    assert response.status_code == 200
    data = response.data["data"]
    assert data["masters_count"] == 2
    assert {m["id"] for m in data["assigned_masters"]} == {str(master.id), str(master2.id)}
    assert data["status"] == OrderStatus.NEW  # assignment does not accept the order
    assert order.assigned_masters.filter(is_active=True).count() == 2


def test_dashboard_assign_saqlash_replaces_master_set(admin_api, master, master2, client_user, service):
    order = make_order(client_user, service)
    admin_api.patch(assign_url(order), {"masters": [str(master.id), str(master2.id)]}, format="json")

    # Re-saving with only master2 (modal Saqlash sends the full selection) drops master.
    response = admin_api.patch(assign_url(order), {"masters": [str(master2.id)]}, format="json")

    data = response.data["data"]
    assert data["masters_count"] == 1
    assert {m["id"] for m in data["assigned_masters"]} == {str(master2.id)}


def test_dashboard_assign_assistants(admin_api, master2, client_user, service):
    order = make_order(client_user, service)

    response = admin_api.patch(assign_url(order), {"assistants": [str(master2.id)]}, format="json")

    assert response.status_code == 200
    data = response.data["data"]
    assert data["assistants_count"] == 1
    assert {a["id"] for a in data["assistants"]} == {str(master2.id)}


# --- Multi-master accept / lead ---------------------------------------------

def test_first_assigned_master_to_accept_becomes_lead(master_api, master2_api, master, master2, client_user, service):
    order = make_order(client_user, service)
    OrderMaster.objects.create(order=order, master=master)
    OrderMaster.objects.create(order=order, master=master2)

    # master2 accepts first -> becomes lead.
    first = master2_api.post(reverse("master-order-accept", args=[order.id]))
    order.refresh_from_db()
    assert first.status_code == 200
    assert order.master == master2
    assert order.status == OrderStatus.ACCEPTED

    # master accepts too -> joins, lead unchanged, status stays accepted.
    second = master_api.post(reverse("master-order-accept", args=[order.id]))
    order.refresh_from_db()
    assert second.status_code == 200
    assert order.master == master2
    assert order.assigned_masters.get(master=master).has_accepted is True


# --- Dashboard status tabs ---------------------------------------------------

def test_dashboard_order_tabs(admin_api, master, client_user, service):
    unassigned = make_order(client_user, service)  # new, no master -> Yangi
    assigned = make_order(client_user, service)
    OrderMaster.objects.create(order=assigned, master=master)  # new + assigned -> Bajarilmoqda
    on_way = make_order(client_user, service, master=master, status=OrderStatus.ON_WAY)
    arrived = make_order(client_user, service, master=master, status=OrderStatus.ARRIVED)
    completed = make_order(client_user, service, master=master, status=OrderStatus.COMPLETED)
    cancelled = make_order(client_user, service, status=OrderStatus.CANCELLED)

    def ids(tab):
        response = admin_api.get(reverse("dashboard-orders"), {"tab": tab})
        assert response.status_code == 200
        return {row["id"] for row in rows(response)}

    assert ids("yangi") == {str(unassigned.id)}
    assert ids("yo'lda") == {str(on_way.id)}
    assert ids("bajarilmoqda") == {str(assigned.id), str(arrived.id)}
    assert ids("yakunlangan") == {str(completed.id)}
    assert ids("bekor") == {str(cancelled.id)}


def test_dashboard_order_status_tab_field(admin_api, client_user, service):
    order = make_order(client_user, service, status=OrderStatus.ARRIVED)

    response = admin_api.get(reverse("dashboard-order-detail", args=[order.id]))

    assert response.status_code == 200
    assert response.data["data"]["status_tab"] == "bajarilmoqda"
