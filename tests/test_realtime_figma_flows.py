import asyncio
import json
import logging
from datetime import date, time
from io import BytesIO
from zipfile import ZipFile

import pytest
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.urls import reverse

from apps.accounts.models import Master
from apps.accounts.tokens import issue_role_tokens
from apps.accounts.ws_auth import RoleJWTAuthMiddleware
from apps.notifications.models import Notification
from apps.notifications.services import create_notification, notification_group

from apps.orders.consumers import ClientTrackingConsumer
from apps.orders.models import HomeBanner, Order, OrderStatus, OrderTracking
from apps.orders.tracking import tracking_group
from apps.support.consumers import serialize_history, ws_json_dumps
from apps.support.models import SupportChat, SupportMessage
from apps.support.services import (
    broadcast_support_message,
    create_support_message,
    get_or_create_support_chat,
    mark_chat_read_by_admin,
    support_group,
)


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


def assign_master(order, master):
    """Simulate the admin assigning a master to an order (dashboard 'Usta biriktirish')."""
    from apps.orders.models import OrderMaster

    return OrderMaster.objects.create(order=order, master=master)


def test_master_only_sees_assigned_orders(master_api, master, client_user, service):
    unassigned = make_order(client_user, service)
    assigned = make_order(client_user, service)
    assign_master(assigned, master)

    response = master_api.get(reverse("master-orders"))

    assert response.status_code == 200
    ids = {item["id"] for item in response.data["results"]}
    assert str(assigned.id) in ids
    assert str(unassigned.id) not in ids  # not assigned to this master


def test_master_accepts_assigned_order(master_api, master, client_user, service):
    order = make_order(client_user, service)
    assign_master(order, master)  # admin assigns

    channel_layer = get_channel_layer()
    client_channel = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(notification_group("client", client_user.id), client_channel)

    list_response = master_api.get(reverse("master-orders"), {"tab": "yangi"})
    accept_response = master_api.post(reverse("master-order-accept", args=[order.id]))

    order.refresh_from_db()

    assert list_response.status_code == 200
    assert str(order.id) in {item["id"] for item in list_response.data["results"]}
    assert accept_response.status_code == 200
    assert OrderTracking.objects.filter(order=order).exists()
    assert order.master == master  # first to accept becomes the lead
    assert order.status == OrderStatus.ACCEPTED
    assert order.assigned_masters.get(master=master).has_accepted is True
    # The client learns of the new status in realtime over the notification socket.
    event = async_to_sync(channel_layer.receive)(client_channel)
    assert event["event"] == "order.status"
    assert event["payload"]["data"]["status"] == OrderStatus.ACCEPTED
    assert event["payload"]["data"]["order_id"] == str(order.id)


def test_master_cannot_accept_unassigned_order(master_api, master, client_user, service):
    order = make_order(client_user, service)  # no assignment

    response = master_api.post(reverse("master-order-accept", args=[order.id]))

    assert response.status_code == 404
    order.refresh_from_db()
    assert order.status == OrderStatus.NEW


def test_client_order_create_opens_tracking_and_status_flow(client_api, master_api, master, client_user, service):
    create_response = client_api.post(
        reverse("client-orders"),
        {
            "service": str(service.id),
            "address_text": "Chilonzor, Tashkent",
            "lat": "41.30000000",
            "lng": "69.25000000",
            "scheduled_date": str(date.today()),
            "scheduled_time": "10:00",
            "payment_type": "cash",
        },
        format="json",
    )
    order = Order.objects.get(client=client_user)
    assign_master(order, master)  # admin assigns the order to the master
    search_track = client_api.get(reverse("client-order-track", args=[order.id]))
    accept_response = master_api.post(reverse("master-order-accept", args=[order.id]))
    accepted_track = client_api.get(reverse("client-order-track", args=[order.id]))
    on_way_response = master_api.post(reverse("master-order-on-way", args=[order.id]))
    on_way_track = client_api.get(reverse("client-order-track", args=[order.id]))
    arrived_response = master_api.post(reverse("master-order-arrived", args=[order.id]))
    arrived_track = client_api.get(reverse("client-order-track", args=[order.id]))
    complete_response = master_api.post(
        reverse("master-order-complete", args=[order.id]),
        {"service_fee": "100000.00"},
        format="json",
    )
    completed_track = client_api.get(reverse("client-order-track", args=[order.id]))

    assert create_response.status_code == 201
    assert OrderTracking.objects.filter(order=order).exists()
    assert search_track.data["data"]["tracking_status"] == "searching_master"
    assert search_track.data["data"]["tracking_status_label"] == "Usta qidirilmoqda"
    assert accept_response.status_code == 200
    assert accepted_track.data["data"]["tracking_status"] == "master_accepted"
    assert accepted_track.data["data"]["tracking_status_label"] == "Usta qabul qildi"
    assert accepted_track.data["data"]["master_contact"]["phone_number"] == master.phone
    assert "chat" not in accepted_track.data["data"]["websocket"]
    assert on_way_response.status_code == 200
    assert on_way_track.data["data"]["tracking_status"] == "master_on_way"
    assert on_way_track.data["data"]["tracking_status_label"] == "Usta yo'lda"
    assert arrived_response.status_code == 200
    assert arrived_track.data["data"]["tracking_status"] == "master_arrived"
    assert arrived_track.data["data"]["tracking_status_label"] == "Usta yetib keldi"
    assert complete_response.status_code == 200
    assert completed_track.data["data"]["tracking_status"] == "master_finished"
    assert completed_track.data["data"]["tracking_status_label"] == "Usta ishni tugatgan"
    assert completed_track.data["data"]["receipt_available"] is True


def test_notification_socket_receives_status_on_master_accept(master_api, master, client_user, service):
    order = make_order(client_user, service)
    assign_master(order, master)
    channel_layer = get_channel_layer()
    channel_name = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(notification_group("client", client_user.id), channel_name)

    response = master_api.post(reverse("master-order-accept", args=[order.id]))
    event = async_to_sync(channel_layer.receive)(channel_name)

    assert response.status_code == 200
    assert event["event"] == "order.status"
    assert event["payload"]["data"]["status"] == OrderStatus.ACCEPTED
    assert event["payload"]["data"]["status_tab"] == "bajarilmoqda"
    assert event["payload"]["data"]["order_id"] == str(order.id)


def test_notification_socket_receives_full_status_flow(master_api, master, client_user, service):
    order = make_order(client_user, service)
    assign_master(order, master)
    channel_layer = get_channel_layer()
    channel_name = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(notification_group("client", client_user.id), channel_name)

    master_api.post(reverse("master-order-accept", args=[order.id]))
    accepted = async_to_sync(channel_layer.receive)(channel_name)
    master_api.post(reverse("master-order-on-way", args=[order.id]))
    on_way = async_to_sync(channel_layer.receive)(channel_name)
    master_api.post(reverse("master-order-arrived", args=[order.id]))
    arrived = async_to_sync(channel_layer.receive)(channel_name)
    master_api.post(
        reverse("master-order-complete", args=[order.id]),
        {"service_fee": "100000.00"},
        format="json",
    )
    completed = async_to_sync(channel_layer.receive)(channel_name)

    # Every transition reaches the client's notification socket in realtime.
    assert [e["event"] for e in (accepted, on_way, arrived, completed)] == ["order.status"] * 4
    assert [
        accepted["payload"]["data"]["status"],
        on_way["payload"]["data"]["status"],
        arrived["payload"]["data"]["status"],
        completed["payload"]["data"]["status"],
    ] == [OrderStatus.ACCEPTED, OrderStatus.ON_WAY, OrderStatus.ARRIVED, OrderStatus.COMPLETED]


def test_status_change_also_notifies_assigned_masters(master_api, master, client_user, service):
    """System A fans every status change out to the assigned master(s) too, not just
    the client — so the lead master and assistants stay in realtime sync."""
    order = make_order(client_user, service)
    assign_master(order, master)
    channel_layer = get_channel_layer()
    master_channel = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(notification_group("master", master.id), master_channel)

    master_api.post(reverse("master-order-accept", args=[order.id]))
    event = async_to_sync(channel_layer.receive)(master_channel)

    assert event["event"] == "order.status"
    assert event["payload"]["data"]["status"] == OrderStatus.ACCEPTED
    assert event["payload"]["data"]["order_id"] == str(order.id)


def test_dashboard_assign_masters_notifies_without_status_change(admin_api, master, client_user, service):
    # Admin assigning masters does NOT accept the order — it stays `new` until a
    # master accepts. So it creates the assignment + notifies the master, and does
    # NOT emit a tracking status event.
    order = make_order(client_user, service)
    channel_layer = get_channel_layer()
    track_channel = async_to_sync(channel_layer.new_channel)()
    master_channel = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(tracking_group(order.id), track_channel)
    async_to_sync(channel_layer.group_add)(notification_group("master", master.id), master_channel)

    response = admin_api.patch(
        reverse("dashboard-order-assign", args=[order.id]),
        {"masters": [str(master.id)]},
        format="json",
    )

    order.refresh_from_db()
    assert response.status_code == 200
    assert order.status == OrderStatus.NEW  # not accepted yet
    assert order.assigned_masters.filter(master=master, is_active=True).exists()
    # The assigned master is notified in realtime (no DB row).
    master_event = async_to_sync(channel_layer.receive)(master_channel)
    assert master_event["payload"]["data"]["order_id"] == str(order.id)

    # Assignment does not change status, so the tracking socket stays silent.
    async def _expect_empty():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(channel_layer.receive(track_channel), timeout=0.2)

    async_to_sync(_expect_empty)()


def test_tracking_socket_silent_without_status_change(master, client_user, service):
    order = make_order(client_user, service, master=master, status=OrderStatus.ACCEPTED)
    channel_layer = get_channel_layer()
    channel_name = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(tracking_group(order.id), channel_name)

    # A non-status change must not emit a tracking event.
    order.note = "keyinroq keling"
    order.save(update_fields=["note", "updated_at"])

    async def _expect_empty():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(channel_layer.receive(channel_name), timeout=0.2)

    async_to_sync(_expect_empty)()


def test_notification_socket_silent_without_status_change(master, client_user, service):
    """The client notification group (sole realtime carrier of status) must stay
    silent unless the status actually changes — guards the from_db/_loaded_status
    marker against phantom/duplicate order.status events on unrelated saves."""
    order = make_order(client_user, service, master=master, status=OrderStatus.ACCEPTED)
    channel_layer = get_channel_layer()
    channel_name = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(notification_group("client", client_user.id), channel_name)

    async def _expect_empty():
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(channel_layer.receive(channel_name), timeout=0.2)

    # A non-status field change must not emit an order.status notification...
    order.note = "keyinroq keling"
    order.save(update_fields=["note", "updated_at"])
    async_to_sync(_expect_empty)()

    # ...nor a re-save with an unchanged status.
    order.status = OrderStatus.ACCEPTED
    order.save(update_fields=["status", "updated_at"])
    async_to_sync(_expect_empty)()


def test_client_tracking_consumer_forwards_master_location():
    # The tracking socket forwards the master's live-location broadcasts to the
    # client (status now travels on the notification socket, not here).
    consumer = ClientTrackingConsumer()
    captured = {}

    async def fake_send(text_data=None, **kwargs):
        captured["text"] = text_data

    consumer.send = fake_send
    event = {
        "type": "tracking.update",
        "event": "master.location",
        "payload": {
            "order_id": "order-1",
            "master_location": {"lat": "41.31", "lng": "69.24"},
        },
    }

    async_to_sync(consumer.tracking_update)(event)

    data = json.loads(captured["text"])
    assert data["type"] == "master.location"
    assert data["data"]["master_location"]["lat"] == "41.31"


def test_client_receipt_download_requires_master_confirmation(client_api, master_api, master, client_user, service):
    order = make_order(
        client_user,
        service,
        master=master,
        status=OrderStatus.COMPLETED,
        service_fee="100000.00",
        total_amount="100000.00",
    )

    blocked_download = client_api.get(reverse("client-order-receipt-download", args=[order.id]))
    confirm_response = master_api.post(reverse("master-order-receipt-confirm", args=[order.id]))
    download_response = client_api.get(reverse("client-order-receipt-download", args=[order.id]))

    order.refresh_from_db()

    assert blocked_download.status_code == 403
    assert confirm_response.status_code == 200
    assert confirm_response.data["data"]["receipt_status"] == "approved"
    assert order.receipt_approved_at is not None
    assert order.receipt_approved_by == master
    assert download_response.status_code == 200
    assert download_response["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "attachment;" in download_response["Content-Disposition"]

    with ZipFile(BytesIO(download_response.content)) as docx:
        document_xml = docx.read("word/document.xml").decode("utf-8")

    assert "HomeX order check" in document_xml
    assert "Chilonzor, Tashkent" in document_xml
    assert service.name in document_xml
    assert master.phone in document_xml


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
    assert track_response.data["data"]["tracking_status"] == "master_accepted"
    assert track_response.data["data"]["master_contact"]["phone_number"] == master.phone


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


def test_notification_realtime_group_receives_create(client_user):
    channel_layer = get_channel_layer()
    channel_name = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(notification_group("client", client_user.id), channel_name)

    before = Notification.objects.count()
    notification = create_notification(role="client", client=client_user, title="Test", body="Realtime")
    created_event = async_to_sync(channel_layer.receive)(channel_name)

    assert created_event["event"] == "notification.created"
    assert created_event["payload"]["id"] == str(notification.id)
    # DB-less: realtime delivery only, nothing persisted (no in-app history).
    assert Notification.objects.count() == before


@pytest.mark.django_db
def test_notification_payload_is_redis_serializable(client_user):
    """Regression: notification broadcasts must survive the Redis (msgpack) layer.

    NotificationSerializer's client/master PrimaryKeyRelatedFields return raw
    UUIDs, which channels_redis (msgpack) cannot pack. notification_payload()
    must normalize them, exactly like the tracking payload does.
    """
    import msgpack

    from apps.notifications.serializers import NotificationSerializer
    from apps.notifications.services import notification_payload

    notification = Notification(role="client", client=client_user, title="X", body="Y")

    # Raw serializer output carries UUIDs -> not msgpack-serializable.
    with pytest.raises(TypeError):
        msgpack.packb(NotificationSerializer(notification).data)

    # notification_payload() normalizes it so the Redis channel layer can pack it.
    msgpack.packb(notification_payload(notification))  # must not raise


def test_support_rest_broadcasts_realtime_event(client_api, client_user):
    channel_layer = get_channel_layer()
    channel_name = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(support_group("client", client_user.id), channel_name)

    response = client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    event = async_to_sync(channel_layer.receive)(channel_name)

    assert response.status_code == 201
    json.dumps(event["payload"])
    assert event["payload"]["message"] == "Yordam kerak"
    assert SupportMessage.objects.filter(client=client_user, message="Yordam kerak").exists()


def test_admin_read_broadcasts_read_receipt_to_participant(client_api, client_user):
    client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    chat = SupportChat.objects.get(client=client_user)

    channel_layer = get_channel_layer()
    channel_name = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(support_group("client", client_user.id), channel_name)

    changed = mark_chat_read_by_admin(chat)
    event = async_to_sync(channel_layer.receive)(channel_name)

    assert changed is True
    assert event["type"] == "chat.read"
    assert event["reader_role"] == "admin"
    assert event["chat_id"] == str(chat.id)
    assert SupportMessage.objects.get(client=client_user, sender_role="client").is_read is True


def test_support_websocket_history_payload_is_json_safe(client_user):
    chat = get_or_create_support_chat(client_user)
    create_support_message(chat=chat, sender=client_user, content="Oldingi xabar")

    history = async_to_sync(serialize_history)(str(chat.id))
    encoded = json.dumps({"type": "history", "messages": history, "chat_id": str(chat.id)})
    ws_encoded = ws_json_dumps({"type": "history", "messages": history, "chat_id": chat.id})
    decoded = json.loads(encoded)

    assert decoded["messages"][0]["chat"] == str(chat.id)
    assert decoded["messages"][0]["client"] == str(client_user.id)
    assert json.loads(ws_encoded)["chat_id"] == str(chat.id)


def test_support_broadcast_failure_is_logged(client_user, monkeypatch, caplog):
    class BrokenChannelLayer:
        async def group_send(self, *args, **kwargs):
            raise RuntimeError("channel layer down")

    chat = get_or_create_support_chat(client_user)
    message = create_support_message(chat=chat, sender=client_user, content="Log test")
    monkeypatch.setattr("apps.support.services.get_channel_layer", lambda: BrokenChannelLayer())

    with caplog.at_level(logging.ERROR, logger="apps.support.services"):
        broadcast_support_message(message)

    assert "Failed to broadcast support message" in caplog.text


def test_client_home_and_map_config_are_frontend_ready(client_api):
    home_response = client_api.get(reverse("client-home"))
    map_response = client_api.get(reverse("client-map-config"))

    assert home_response.status_code == 200
    assert "websocket" in home_response.data["data"]
    assert "quick_actions" in home_response.data["data"]
    assert set(home_response.data["data"]["banners"][0]) == {"id", "banner_image", "banner_url", "is_active"}
    assert map_response.status_code == 200
    assert map_response.data["data"]["tracking_ws_template"] == "/ws/client/track/{order_id}/"
    assert map_response.data["data"]["auth_header"] == "Authorization: Bearer {access_token}"


def test_client_home_anonymous_user_only_gets_public_payload(api_client, service):
    response = api_client.get(reverse("client-home"))

    assert response.status_code == 200
    assert set(response.data["data"]) == {"services", "banners"}
    assert response.data["data"]["services"][0]["name"] == service.category.name
    assert set(response.data["data"]["banners"][0]) == {"id", "banner_image", "banner_url", "is_active"}


def test_client_home_banner_image_is_exposed_in_api(client_api):
    HomeBanner.objects.update(is_active=False)
    HomeBanner.objects.create(banner_image="home/banners/mobile-banner.jpg")

    response = client_api.get(reverse("client-home"))

    banner = response.data["data"]["banners"][0]
    assert response.status_code == 200
    assert banner["banner_image"].endswith("/media/home/banners/mobile-banner.jpg")
    assert banner["banner_url"] == banner["banner_image"]


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
