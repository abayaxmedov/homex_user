"""End-to-end tests for the client order-tracking WebSocket.

Simulates the real app flow through the full ASGI stack (JWT auth middleware +
URL routing), the same way `ws/client/support/` is exercised:

  1. Client connects to ``ws/client/track/<order_id>/`` -> gets a snapshot.
  2. Master connects to ``ws/master/tracking/`` and sends lat/lng -> the client
     receives ``master.location`` in realtime.
  3. Order status changes (accept/start/...) -> the client receives
     ``tracking.update``.
"""
import asyncio
import json
from datetime import date, time

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from asgiref.testing import ApplicationCommunicator
from channels.routing import URLRouter

from channels.layers import get_channel_layer

from apps.accounts.tokens import issue_role_tokens
from apps.accounts.ws_auth import RoleJWTAuthMiddleware
from apps.orders.models import Order, OrderStatus
from apps.orders.tracking import tracking_group
from config.routing import websocket_urlpatterns


TIMEOUT = 3


class WebsocketCommunicator(ApplicationCommunicator):
    """Minimal stand-in for channels.testing.WebsocketCommunicator.

    (channels.testing imports daphne, which this project intentionally does
    not install — production runs uvicorn.)
    """

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

    async def send_to(self, text_data):
        await self.send_input({"type": "websocket.receive", "text": text_data})

    async def receive_from(self, timeout=1):
        response = await self.receive_output(timeout)
        assert response["type"] == "websocket.send", f"expected websocket.send, got {response}"
        return response.get("text")

    async def disconnect(self, code=1000, timeout=1):
        await self.send_input({"type": "websocket.disconnect", "code": code})
        await self.wait(timeout)


def make_app():
    return RoleJWTAuthMiddleware(URLRouter(websocket_urlpatterns))


def bearer_headers(user, role):
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


async def connect_client_track(order, client_user):
    communicator = WebsocketCommunicator(
        make_app(), f"/ws/client/track/{order.id}/", headers=bearer_headers(client_user, "client")
    )
    connected, _ = await communicator.connect(timeout=TIMEOUT)
    assert connected, "client tracking socket did not accept the connection"
    snapshot = json.loads(await communicator.receive_from(timeout=TIMEOUT))
    assert snapshot["type"] == "tracking.snapshot"
    return communicator, snapshot


async def connect_client_notifications(client_user):
    communicator = WebsocketCommunicator(
        make_app(), "/ws/client/notifications/", headers=bearer_headers(client_user, "client")
    )
    connected, _ = await communicator.connect(timeout=TIMEOUT)
    assert connected, "client notification socket did not accept the connection"
    return communicator


@pytest.mark.django_db
def test_tracking_broadcast_payload_is_redis_serializable(client_user, master, service):
    """Regression: broadcasts must survive the Redis channel layer.

    channels_redis packs group messages with msgpack, which cannot encode the
    UUID/Decimal values tracking_payload() carries. Without json_safe() the
    broadcast raised "can not serialize 'UUID' object" and no realtime arrived
    (the bug was masked by the InMemory layer used in the other tests).
    """
    import msgpack

    from apps.orders.tracking import json_safe, tracking_payload

    order = make_order(client_user, service, master=master, status=OrderStatus.ACCEPTED)
    payload = tracking_payload(order)

    # Raw payload (UUID order_id, Decimal lat/lng) is NOT msgpack-serializable.
    with pytest.raises(TypeError):
        msgpack.packb(payload)

    # json_safe() normalizes it so the Redis channel layer can broadcast it.
    msgpack.packb(json_safe(payload))  # must not raise


@pytest.mark.django_db(transaction=True)
def test_client_track_ws_receives_master_location_from_master_ws(client_user, master, service):
    order = make_order(client_user, service, master=master, status=OrderStatus.ACCEPTED)

    async def scenario():
        client_ws, snapshot = await connect_client_track(order, client_user)
        master_ws = WebsocketCommunicator(
            make_app(), "/ws/master/tracking/", headers=bearer_headers(master, "master")
        )
        connected, _ = await master_ws.connect(timeout=TIMEOUT)
        assert connected, "master tracking socket did not accept the connection"

        # Master streams a location tied to the order -> client must get it live.
        await master_ws.send_to(
            json.dumps({"lat": "41.311081", "lng": "69.240562", "order_id": str(order.id)})
        )
        ack = json.loads(await master_ws.receive_from(timeout=TIMEOUT))
        assert ack["type"] == "master.location.saved"

        event = json.loads(await client_ws.receive_from(timeout=TIMEOUT))
        assert event["type"] == "master.location"
        assert event["data"]["master_location"]["lat"] is not None

        await client_ws.disconnect()
        await master_ws.disconnect()
        return snapshot

    snapshot = async_to_sync(scenario)()
    assert snapshot["data"]["status"] == OrderStatus.ACCEPTED


@pytest.mark.django_db(transaction=True)
def test_client_track_ws_receives_master_location_without_order_id(client_user, master, service):
    """The master app often streams bare {lat, lng} without order_id.

    The client watching the master's active order must still get the update —
    this mirrors how the support chat broadcasts to every interested group.
    """
    order = make_order(client_user, service, master=master, status=OrderStatus.ACCEPTED)

    async def scenario():
        client_ws, _ = await connect_client_track(order, client_user)
        master_ws = WebsocketCommunicator(
            make_app(), "/ws/master/tracking/", headers=bearer_headers(master, "master")
        )
        connected, _ = await master_ws.connect(timeout=TIMEOUT)
        assert connected

        await master_ws.send_to(json.dumps({"lat": "41.311081", "lng": "69.240562"}))
        ack = json.loads(await master_ws.receive_from(timeout=TIMEOUT))
        assert ack["type"] == "master.location.saved"

        event = json.loads(await client_ws.receive_from(timeout=TIMEOUT))
        assert event["type"] == "master.location"

        await client_ws.disconnect()
        await master_ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_status_change_arrives_on_notification_socket_not_tracking(client_user, master, service):
    """Status changes are realtime on the NOTIFICATION socket, not the tracking one.

    The tracking socket is location-only now: any code path that saves a status
    change pushes an ``order.status`` event to the client's notification socket
    (no refresh, no DB write) and must NOT surface on the tracking socket.
    """
    order = make_order(client_user, service)

    async def scenario():
        notif_ws = await connect_client_notifications(client_user)

        # Watch the tracking group directly to prove status does NOT go there.
        channel_layer = get_channel_layer()
        track_channel = await channel_layer.new_channel()
        await channel_layer.group_add(tracking_group(order.id), track_channel)

        # Master accepts the order (any code path that saves a status change).
        def accept():
            fresh = Order.objects.get(pk=order.pk)
            fresh.master = master
            fresh.status = OrderStatus.ACCEPTED
            fresh.save()

        await sync_to_async(accept)()

        # Lands on the notification socket in realtime. The WS envelope is
        # {type, data: <notification>}, and the domain payload sits in
        # notification.data (order_id/status/...).
        event = json.loads(await notif_ws.receive_from(timeout=TIMEOUT))
        assert event["type"] == "order.status"
        assert event["data"]["data"]["status"] == OrderStatus.ACCEPTED
        assert event["data"]["data"]["order_id"] == str(order.id)
        assert event["data"]["data"]["status_tab"] == "bajarilmoqda"

        # ...and NOT on the tracking group (it only carries the master's location).
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(channel_layer.receive(track_channel), timeout=0.3)

        await notif_ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_rest_location_update_without_order_id_broadcasts(client_user, master, service, master_api):
    """The REST fallback must fan out to active orders exactly like the WS path."""
    from django.urls import reverse

    order = make_order(client_user, service, master=master, status=OrderStatus.ACCEPTED)

    async def scenario():
        client_ws, _ = await connect_client_track(order, client_user)

        def rest_ping():
            response = master_api.post(
                reverse("master-location-update"),
                {"lat": "41.311081", "lng": "69.240562"},
                format="json",
            )
            assert response.status_code == 200

        await sync_to_async(rest_ping)()

        event = json.loads(await client_ws.receive_from(timeout=TIMEOUT))
        assert event["type"] == "master.location"

        await client_ws.disconnect()

    async_to_sync(scenario)()


@pytest.mark.django_db(transaction=True)
def test_master_ws_survives_malformed_payload(client_user, master, service):
    """A bad frame must not kill the socket (support chat behaves this way)."""
    order = make_order(client_user, service, master=master, status=OrderStatus.ACCEPTED)

    async def scenario():
        master_ws = WebsocketCommunicator(
            make_app(), "/ws/master/tracking/", headers=bearer_headers(master, "master")
        )
        connected, _ = await master_ws.connect(timeout=TIMEOUT)
        assert connected

        await master_ws.send_to("not-json{{{")
        error = json.loads(await master_ws.receive_from(timeout=TIMEOUT))
        assert error["type"] == "error"

        # Socket must stay open and keep working afterwards.
        await master_ws.send_to(
            json.dumps({"lat": "41.311081", "lng": "69.240562", "order_id": str(order.id)})
        )
        ack = json.loads(await master_ws.receive_from(timeout=TIMEOUT))
        assert ack["type"] == "master.location.saved"

        await master_ws.disconnect()

    async_to_sync(scenario)()
