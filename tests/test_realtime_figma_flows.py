from datetime import date, time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.urls import reverse

from apps.accounts.models import Master
from apps.accounts.tokens import issue_role_tokens
from apps.accounts.ws_auth import RoleJWTAuthMiddleware
from apps.notifications.models import Notification
from apps.notifications.services import create_notification, notification_group
from apps.orders.models import Order, OrderStatus, OrderTracking
from apps.support.models import SupportMessage
from apps.support.services import support_group


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


def test_master_sees_and_accepts_unassigned_order(master_api, master, client_user, service):
    order = make_order(client_user, service)

    list_response = master_api.get(reverse("master-orders"), {"tab": "yangi"})
    accept_response = master_api.post(reverse("master-order-accept", args=[order.id]))

    order.refresh_from_db()

    assert list_response.status_code == 200
    assert str(order.id) in {item["id"] for item in list_response.data["results"]}
    assert accept_response.status_code == 200
    assert order.master == master
    assert order.status == OrderStatus.ACCEPTED
    assert Notification.objects.filter(client=client_user, data__order_id=str(order.id)).exists()


def test_tracking_location_update_and_client_track_payload(master_api, client_api, master, client_user, service):
    order = make_order(client_user, service, master=master, status=OrderStatus.ACCEPTED)

    response = master_api.post(
        reverse("master-location-update"),
        {
            "lat": "41.30100000",
            "lng": "69.25100000",
            "order_id": str(order.id),
        },
        format="json",
    )
    track_response = client_api.get(reverse("client-order-track", args=[order.id]))

    master.refresh_from_db()
    tracking = OrderTracking.objects.get(order=order)

    assert response.status_code == 200
    assert master.is_online is True
    assert tracking.master_lat is not None
    assert track_response.status_code == 200
    assert track_response.data["data"]["master_location"]["lat"] == tracking.master_lat
    assert track_response.data["data"]["distance_km"] is not None


def test_nearby_masters_return_distance_and_eta(client_api, master):
    master.is_online = True
    master.is_available = True
    master.lat = "41.30100000"
    master.lng = "69.25100000"
    master.save()
    Master.objects.create(
        phone="+998901112244",
        first_name="Far",
        password="1234",
        is_online=True,
        is_available=True,
        lat="40.00000000",
        lng="68.00000000",
    )

    response = client_api.get(
        reverse("client-nearby-masters"),
        {"lat": "41.30000000", "lng": "69.25000000", "radius_km": "5"},
    )

    assert response.status_code == 200
    assert len(response.data["data"]) == 1
    assert response.data["data"][0]["distance_km"] is not None
    assert response.data["data"][0]["eta_minutes"] is not None


def test_notification_realtime_group_receives_create_and_read(client_api, client_user):
    channel_layer = get_channel_layer()
    channel_name = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(notification_group("client", client_user.id), channel_name)

    notification = create_notification(role="client", client=client_user, title="Test", body="Realtime")
    created_event = async_to_sync(channel_layer.receive)(channel_name)
    read_response = client_api.patch(reverse("client-notification-read", args=[notification.id]))
    read_event = async_to_sync(channel_layer.receive)(channel_name)

    assert created_event["event"] == "notification.created"
    assert created_event["payload"]["id"] == str(notification.id)
    assert read_response.status_code == 200
    assert read_event["event"] == "notification.read"
    assert read_event["payload"]["is_read"] is True


def test_support_rest_broadcasts_realtime_event(client_api, client_user):
    channel_layer = get_channel_layer()
    channel_name = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(support_group("client", client_user.id), channel_name)

    response = client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    event = async_to_sync(channel_layer.receive)(channel_name)

    assert response.status_code == 201
    assert event["payload"]["message"] == "Yordam kerak"
    assert SupportMessage.objects.filter(client=client_user, message="Yordam kerak").exists()


def test_client_home_and_map_config_are_frontend_ready(client_api):
    home_response = client_api.get(reverse("client-home"))
    map_response = client_api.get(reverse("client-map-config"))

    assert home_response.status_code == 200
    assert "websocket" in home_response.data["data"]
    assert "quick_actions" in home_response.data["data"]
    assert map_response.status_code == 200
    assert map_response.data["data"]["tracking_ws_template"] == "/ws/client/track/{order_id}/"
    assert map_response.data["data"]["auth_header"] == "Authorization: Bearer {access_token}"


def test_websocket_auth_reads_authorization_header_not_query(master):
    captured = {}

    async def app(scope, receive, send):
        captured["user"] = scope["user"]

    middleware = RoleJWTAuthMiddleware(app)
    token = issue_role_tokens(master, "master")["access_token"]

    async_to_sync(middleware)(
        {"headers": [(b"authorization", f"Bearer {token}".encode())], "query_string": b""},
        None,
        None,
    )
    assert captured["user"] == master

    async_to_sync(middleware)(
        {"headers": [], "query_string": f"token={token}".encode()},
        None,
        None,
    )
    assert captured["user"] is None
