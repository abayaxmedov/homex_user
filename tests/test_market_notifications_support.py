from django.urls import reverse

from apps.accounts.models import Client, FCMDevice
from apps.market.models import MarketCategory, MarketFavorite, MarketOrder, MarketProduct
from apps.notifications.models import Notification
from apps.notifications.services import create_notification
from apps.support.admin import SupportChatAdmin
from apps.support.models import SupportChat, SupportMessage
from apps.support.serializers import SupportChatSerializer
from apps.support.services import (
    attach_latest_support_messages,
    create_support_message,
    mark_chat_read_by_admin,
    with_latest_support_message,
)


def test_market_product_order_favorite_and_listing(client_api, client_user):
    category = MarketCategory.objects.create(name="Quvurlar", slug="quvurlar")
    product = MarketProduct.objects.create(
        category=category,
        name="PVC quvur",
        description="20mm",
        condition=MarketProduct.NEW,
        price=25000,
        quantity=10,
    )

    products = client_api.get(reverse("client-market-products"), {"search": "PVC"})
    order = client_api.post(
        reverse("client-market-orders"),
        {
            "product": str(product.id),
            "quantity": 2,
            "delivery_address": "Tashkent",
            "phone": "+998901234567",
            "note": "",
        },
        format="json",
    )
    favorite = client_api.post(reverse("client-market-favorite-toggle"), {"product": str(product.id)}, format="json")
    listing = client_api.post(
        reverse("client-market-listing-create"),
        {
            "category": str(category.id),
            "name": "Ishlatilgan ventil",
            "description": "",
            "condition": MarketProduct.USED,
            "price": "10000",
            "quantity": 1,
        },
        format="json",
    )

    assert products.status_code == 200
    assert order.status_code == 201
    assert favorite.status_code == 201
    assert listing.status_code == 201
    assert MarketOrder.objects.get(client=client_user).total_amount == 50000
    assert MarketFavorite.objects.filter(client=client_user, product=product).exists()
    assert MarketProduct.objects.get(name="Ishlatilgan ventil").is_moderated is False


def test_market_categories_are_listed(client_api):
    MarketCategory.objects.create(name="Quvurlar", slug="quvurlar")
    MarketCategory.objects.create(name="Asboblar", slug="asboblar")

    response = client_api.get(reverse("client-market-categories"))

    assert response.status_code == 200
    assert response.data["success"] is True
    assert [category["slug"] for category in response.data["data"]] == ["asboblar", "quvurlar"]
    assert response.data["data"][0]["products_count"] == 0


def test_market_products_can_be_filtered_by_category_and_searched(client_api):
    parts = MarketCategory.objects.create(name="Qismlar", slug="qismlar")
    tools = MarketCategory.objects.create(name="Uskunalar", slug="uskunalar")
    filter_product = MarketProduct.objects.create(
        category=parts,
        name="Filtr",
        description="Suv filtri",
        condition=MarketProduct.NEW,
        price=25000,
        quantity=3,
    )
    MarketProduct.objects.create(
        category=tools,
        name="Drel",
        description="Elektr uskuna",
        condition=MarketProduct.USED,
        price=200000,
        quantity=1,
    )

    by_slug = client_api.get(reverse("client-market-products"), {"category": "qismlar"})
    by_id = client_api.get(reverse("client-market-products"), {"category": str(parts.id)})
    search = client_api.get(reverse("client-market-product-search"), {"q": "filtr"})
    empty = client_api.get(reverse("client-market-product-search"), {"q": "nasos"})
    categories = client_api.get(reverse("client-market-categories"))

    assert by_slug.status_code == 200
    assert by_slug.data["count"] == 1
    assert by_slug.data["results"][0]["id"] == str(filter_product.id)
    assert by_id.data["count"] == 1
    assert search.status_code == 200
    assert search.data["count"] == 1
    assert search.data["results"][0]["name"] == "Filtr"
    assert empty.status_code == 200
    assert empty.data["count"] == 0
    counts = {category["slug"]: category["products_count"] for category in categories.data["data"]}
    assert counts == {"qismlar": 1, "uskunalar": 1}


def test_socket_notifications_are_realtime_only_and_not_persisted(client_user, master):
    """System A (socket notifications): active-order/status events are delivered
    over the WS group + FCM to BOTH roles and are NEVER written to the DB, so they
    never surface in the persisted admin-notification list.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from apps.notifications.services import notification_group

    channel_layer = get_channel_layer()
    client_channel = async_to_sync(channel_layer.new_channel)()
    master_channel = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(notification_group("client", client_user.id), client_channel)
    async_to_sync(channel_layer.group_add)(notification_group("master", master.id), master_channel)

    before = Notification.objects.count()
    create_notification(role="client", client=client_user, title="Buyurtma", body="Qabul qilindi")
    create_notification(role="master", master=master, title="Yangi buyurtma", body="Sizga buyurtma biriktirildi")

    client_event = async_to_sync(channel_layer.receive)(client_channel)
    master_event = async_to_sync(channel_layer.receive)(master_channel)

    assert client_event["event"] == "notification.created"
    assert client_event["payload"]["title"] == "Buyurtma"
    assert master_event["payload"]["title"] == "Yangi buyurtma"
    # DB-less: nothing was persisted.
    assert Notification.objects.count() == before


def test_admin_db_notifications_are_listed_and_readable_socket_ones_are_not(client_api, master_api, client_user, master):
    """System B (admin/DB notifications): admin-authored notifications ARE persisted
    and exposed via the REST list/read endpoints with unread state — kept SEPARATE
    from the DB-less realtime status stream (System A), which must not appear here.
    """
    # System B: admin-authored, persisted.
    client_admin = Notification.objects.create(role="client", client=client_user, title="Admin e'lon", body="hammaga")
    master_admin = Notification.objects.create(role="master", master=master, title="Admin e'lon", body="ustalarga")
    # System A: realtime status, DB-less — must NOT leak into the REST list.
    create_notification(
        role="client", client=client_user, title="Usta yo'lda", event="order.status",
        data={"order_id": "x", "status": "on_way"},
    )

    client_list = client_api.get(reverse("client-notifications"))
    master_list = master_api.get(reverse("master-notifications"))
    assert client_list.status_code == 200 and master_list.status_code == 200

    def titles(resp):
        body = resp.data.get("results")
        if body is None:
            body = resp.data.get("data", resp.data)
        return [n["title"] for n in body]

    assert "Admin e'lon" in titles(client_list)
    assert "Usta yo'lda" not in titles(client_list)  # the socket/status event is not persisted or listed
    assert "Admin e'lon" in titles(master_list)

    # read marks the persisted admin notification (System B) as read.
    read = client_api.patch(reverse("client-notification-read", args=[client_admin.id]))
    assert read.status_code == 200
    client_admin.refresh_from_db()
    assert client_admin.is_read is True
    master_admin.refresh_from_db()  # untouched
    assert master_admin.is_read is False


def test_client_push_register_is_idempotent(client_api, client_user):
    first = client_api.post(
        reverse("client-push-register"),
        {"token": " client-fcm-token ", "platform": "ios"},
        format="json",
    )
    second = client_api.post(
        reverse("client-push-register"),
        {"token": "client-fcm-token", "platform": "android"},
        format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert FCMDevice.objects.count() == 1
    device = FCMDevice.objects.get()
    assert device.client == client_user
    assert device.role == "client"
    assert device.platform == "android"
    assert device.is_active is True
    client_user.refresh_from_db()
    assert client_user.fcm_token == "client-fcm-token"


def test_create_notification_sends_push_to_active_devices(
    monkeypatch, client_user, django_capture_on_commit_callbacks
):
    sent = {}

    class FakePushClient:
        def send_many(self, tokens, title, body, data=None):
            sent.update({"tokens": tokens, "title": title, "body": body, "data": data})

    monkeypatch.setattr("apps.notifications.services.PushClient", lambda: FakePushClient())
    FCMDevice.objects.create(role="client", client=client_user, token="active-token", platform="ios")
    FCMDevice.objects.create(
        role="client",
        client=client_user,
        token="inactive-token",
        platform="android",
        is_active=False,
    )

    # The push is deferred to transaction.on_commit, so run the callbacks.
    with django_capture_on_commit_callbacks(execute=True):
        notification = create_notification(
            role="client",
            client=client_user,
            title="Buyurtma",
            body="Qabul qilindi",
            data={"order_id": "123"},
        )

    assert sent["tokens"] == ["active-token"]
    assert sent["title"] == "Buyurtma"
    assert sent["body"] == "Qabul qilindi"
    assert sent["data"]["notification_id"] == str(notification.id)
    assert sent["data"]["order_id"] == "123"


def test_create_notification_respects_push_setting(monkeypatch, client_user):
    client_user.push_enabled = False
    client_user.save(update_fields=["push_enabled"])
    FCMDevice.objects.create(role="client", client=client_user, token="active-token", platform="ios")
    sent = []

    class FakePushClient:
        def send_many(self, tokens, title, body, data=None):
            sent.append(tokens)

    monkeypatch.setattr("apps.notifications.services.PushClient", lambda: FakePushClient())
    create_notification(role="client", client=client_user, title="Buyurtma")

    assert sent == []


def test_support_messages_are_scoped_by_role(client_api, master_api, client_user, master):
    client_response = client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    master_response = master_api.post(reverse("master-support"), {"message": "Buyurtma savoli"}, format="json")

    assert client_response.status_code == 201
    assert master_response.status_code == 201
    assert SupportMessage.objects.filter(client=client_user, sender_role="client").exists()
    assert SupportMessage.objects.filter(master=master, sender_role="master").exists()


def test_support_chat_tracks_history_unread_and_admin_reply(client_api, client_user, django_admin_user):
    create_response = client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    chat = SupportChat.objects.get(client=client_user)

    history_response = client_api.get(reverse("client-support"))
    reply = create_support_message(chat=chat, sender=django_admin_user, content="Admin javobi")
    chat.refresh_from_db()
    unread_after_reply = chat.unread_by_admin
    marked = mark_chat_read_by_admin(chat)
    chat.refresh_from_db()

    assert create_response.status_code == 201
    assert history_response.status_code == 200
    assert str(history_response.data["results"][0]["chat"]) == str(chat.id)
    assert history_response.data["results"][0]["content"] == "Yordam kerak"
    assert reply.sender_role == "admin"
    assert reply.client == client_user
    assert unread_after_reply == 1
    assert marked is True
    assert chat.unread_by_admin == 0


def test_dashboard_admin_reply_reaches_client_thread(admin_api, client_api, client_user, django_admin_user):
    """Admin reply sent through the dashboard REST endpoint must be attached to
    the participant's SupportChat — the client app reads the thread through the
    ``chat`` FK, so an orphan (chat=NULL) message never reaches the user."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from apps.support.services import support_group

    # Subscribe to the client's support group the same way the consumer does,
    # so we can assert the dashboard reply is broadcast in realtime too.
    channel_layer = get_channel_layer()
    client_channel = async_to_sync(channel_layer.new_channel)()
    async_to_sync(channel_layer.group_add)(support_group("client", client_user.id), client_channel)

    response = admin_api.post(
        reverse("dashboard-support-messages"),
        {"client": str(client_user.id), "message": "Admin dashboard javobi", "sender_role": "admin"},
        format="json",
    )
    assert response.status_code == 201

    message = SupportMessage.objects.get(sender_role="admin", client=client_user)
    chat = SupportChat.objects.get(client=client_user)
    assert message.chat_id == chat.id
    assert message.admin == django_admin_user

    history = client_api.get(reverse("client-support"))
    assert history.status_code == 200
    contents = [row["content"] for row in history.data["results"]]
    assert "Admin dashboard javobi" in contents

    event = async_to_sync(channel_layer.receive)(client_channel)
    assert event["type"] == "chat.message"
    assert event["message"]["content"] == "Admin dashboard javobi"
