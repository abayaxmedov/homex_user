import json
from datetime import date, time, timedelta

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from asgiref.testing import ApplicationCommunicator
from channels.routing import URLRouter
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.tokens import issue_role_tokens
from apps.accounts.ws_auth import RoleJWTAuthMiddleware
from apps.orders.models import Order, OrderStatus
from config.routing import websocket_urlpatterns


TIMEOUT = 3


class WebsocketCommunicator(ApplicationCommunicator):
    def __init__(self, application, path, headers=None):
        scope = {
            "type": "websocket",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": headers or [],
            "subprotocols": [],
        }
        super().__init__(application, scope)

    async def connect(self, timeout=1):
        await self.send_input({"type": "websocket.connect"})
        response = await self.receive_output(timeout)
        if response["type"] == "websocket.close":
            return False, response.get("code", 1000)
        assert response["type"] == "websocket.accept"
        return True, response.get("subprotocol")

    async def receive_from(self, timeout=1):
        response = await self.receive_output(timeout)
        assert response["type"] == "websocket.send", f"expected websocket.send, got {response}"
        return response.get("text")

    async def disconnect(self, code=1000, timeout=1):
        await self.send_input({"type": "websocket.disconnect", "code": code})
        await self.wait(timeout)


def make_app():
    return RoleJWTAuthMiddleware(URLRouter(websocket_urlpatterns))


def dashboard_headers(user):
    access = AccessToken()
    access.set_exp(from_time=timezone.now(), lifetime=timedelta(days=settings.ACCESS_TOKEN_DAYS))
    access["sub"] = str(user.id)
    access["role"] = "admin"
    access["username"] = user.get_username()
    return [(b"authorization", f"Bearer {access}".encode())]


def role_headers(user, role):
    token = issue_role_tokens(user, role)["access_token"]
    return [(b"authorization", f"Bearer {token}".encode())]


def make_order(client_user, service, **kwargs):
    defaults = {
        "client": client_user,
        "service": service,
        "address_text": "Chilonzor, Tashkent",
        "lat": "41.30000000",
        "lng": "69.25000000",
        "scheduled_date": date.today(),
        "scheduled_time": time(10, 0),
    }
    defaults.update(kwargs)
    return Order.objects.create(**defaults)


@pytest.mark.django_db(transaction=True)
def test_dashboard_orders_ws_accepts_staff_header_token_only(django_admin_user, client_user, master):
    async def scenario():
        admin_ws = WebsocketCommunicator(
            make_app(),
            "/ws/dashboard/orders/",
            headers=dashboard_headers(django_admin_user),
        )
        connected, _ = await admin_ws.connect(timeout=TIMEOUT)
        assert connected
        await admin_ws.disconnect()

        for headers in ([], role_headers(client_user, "client"), role_headers(master, "master")):
            ws = WebsocketCommunicator(make_app(), "/ws/dashboard/orders/", headers=headers)
            connected, _ = await ws.connect(timeout=TIMEOUT)
            assert connected is False

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_dashboard_orders_ws_receives_order_created(django_admin_user, client_user, service):
    async def scenario():
        ws = WebsocketCommunicator(
            make_app(),
            "/ws/dashboard/orders/",
            headers=dashboard_headers(django_admin_user),
        )
        connected, _ = await ws.connect(timeout=TIMEOUT)
        assert connected

        order = await sync_to_async(make_order)(client_user, service)

        event = json.loads(await ws.receive_from(timeout=TIMEOUT))
        assert event["type"] == "order.created"
        assert event["data"]["order_id"] == str(order.id)
        assert event["data"]["status"] == OrderStatus.NEW
        assert event["data"]["status_tab"] == "yangi"
        await ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_dashboard_orders_ws_receives_order_status_changed(django_admin_user, client_user, master, service):
    order = make_order(client_user, service)

    async def scenario():
        ws = WebsocketCommunicator(
            make_app(),
            "/ws/dashboard/orders/",
            headers=dashboard_headers(django_admin_user),
        )
        connected, _ = await ws.connect(timeout=TIMEOUT)
        assert connected

        def accept_order():
            fresh = Order.objects.get(pk=order.pk)
            fresh.master = master
            fresh.status = OrderStatus.ACCEPTED
            fresh.save(update_fields=["master", "status", "updated_at"])

        await sync_to_async(accept_order)()

        event = json.loads(await ws.receive_from(timeout=TIMEOUT))
        assert event["type"] == "order.status_changed"
        assert event["data"]["order_id"] == str(order.id)
        assert event["data"]["old_status"] == OrderStatus.NEW
        assert event["data"]["status"] == OrderStatus.ACCEPTED
        assert event["data"]["status_tab"] == "bajarilmoqda"
        assert event["data"]["master_id"] == str(master.id)
        await ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_dashboard_orders_ws_receives_order_master_changed(django_admin_user, client_user, master, service):
    order = make_order(client_user, service)

    async def scenario():
        ws = WebsocketCommunicator(
            make_app(),
            "/ws/dashboard/orders/",
            headers=dashboard_headers(django_admin_user),
        )
        connected, _ = await ws.connect(timeout=TIMEOUT)
        assert connected

        def assign_master():
            api = APIClient()
            api.force_authenticate(user=django_admin_user)
            return api.patch(
                reverse("dashboard-order-assign", args=[order.id]),
                {"masters": [str(master.id)]},
                format="json",
            )

        response = await sync_to_async(assign_master)()
        assert response.status_code == 200

        event = json.loads(await ws.receive_from(timeout=TIMEOUT))
        assert event["type"] == "order.master_changed"
        assert event["data"]["order_id"] == str(order.id)
        assert str(master.id) in event["data"]["assigned_master_ids"]
        await ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_dashboard_orders_ws_receives_master_status_changed(django_admin_user, client_user, master, service):
    order = make_order(client_user, service, master=master, status=OrderStatus.ACCEPTED)

    async def scenario():
        ws = WebsocketCommunicator(
            make_app(),
            "/ws/dashboard/orders/",
            headers=dashboard_headers(django_admin_user),
        )
        connected, _ = await ws.connect(timeout=TIMEOUT)
        assert connected

        def set_master_busy():
            api = APIClient()
            api.force_authenticate(user=django_admin_user)
            return api.patch(
                reverse("dashboard-master-status", args=[master.id]),
                {"status": "busy"},
                format="json",
            )

        response = await sync_to_async(set_master_busy)()
        assert response.status_code == 200

        event = json.loads(await ws.receive_from(timeout=TIMEOUT))
        assert event["type"] == "master.status_changed"
        assert event["data"]["master_id"] == str(master.id)
        assert event["data"]["master_status"] == "busy"
        assert str(order.id) in event["data"]["order_ids"]
        await ws.disconnect()

    async_to_sync(scenario)()
