from django.contrib.admin.sites import site as admin_site
from django.test import RequestFactory
from django.urls import reverse

from apps.accounts.models import FCMDevice
from apps.market.models import MarketCategory, MarketFavorite, MarketOrder, MarketProduct
from apps.notifications.models import Notification
from apps.notifications.services import create_notification
from apps.support.admin import SupportChatAdmin
from apps.support.models import SupportChat, SupportMessage
from apps.support.services import create_support_message, mark_chat_read_by_admin


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


def test_notifications_can_be_read_by_role(client_api, master_api, client_user, master):
    client_notification = Notification.objects.create(
        role="client",
        client=client_user,
        title="Buyurtma",
        body="Qabul qilindi",
    )
    master_notification = Notification.objects.create(
        role="master",
        master=master,
        title="Yangi buyurtma",
        body="Sizga buyurtma biriktirildi",
    )

    client_list = client_api.get(reverse("client-notifications"))
    client_read = client_api.patch(reverse("client-notification-read", args=[client_notification.id]))
    master_list = master_api.get(reverse("master-notifications"))
    master_read = master_api.patch(reverse("master-notification-read", args=[master_notification.id]))

    assert client_list.status_code == 200
    assert client_read.status_code == 200
    assert master_list.status_code == 200
    assert master_read.status_code == 200
    client_notification.refresh_from_db()
    master_notification.refresh_from_db()
    assert client_notification.is_read is True
    assert master_notification.is_read is True


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


def test_create_notification_sends_push_to_active_devices(monkeypatch, client_user):
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
    assert chat.messages.get(sender_role="client").is_read is True


def test_admin_read_marks_incoming_messages_but_not_admin_reply(client_api, client_user, django_admin_user):
    client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    chat = SupportChat.objects.get(client=client_user)
    admin_reply = create_support_message(chat=chat, sender=django_admin_user, content="Admin javobi")
    incoming = SupportMessage.objects.get(chat=chat, sender_role="client")

    assert incoming.is_read is False  # unread until the admin opens the chat

    changed = mark_chat_read_by_admin(chat)

    incoming.refresh_from_db()
    admin_reply.refresh_from_db()
    chat.refresh_from_db()
    assert changed is True
    assert incoming.is_read is True  # participant message is now marked read
    assert admin_reply.is_read is False  # admin's own reply is untouched
    assert chat.unread_by_admin == 0
    # Re-reading an already-read chat is a no-op and reports no change.
    assert mark_chat_read_by_admin(chat) is False


def test_dashboard_opening_thread_marks_incoming_messages_read(admin_api, client_api, client_user):
    client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    incoming = SupportMessage.objects.get(client=client_user, sender_role="client")
    assert incoming.is_read is False

    response = admin_api.get(reverse("dashboard-support-messages"), {"client": str(client_user.id)})

    assert response.status_code == 200
    incoming.refresh_from_db()
    assert incoming.is_read is True  # opening the thread read the message

    threads = admin_api.get(reverse("dashboard-support-threads"))
    assert threads.status_code == 200
    assert threads.data["data"]["results"][0]["unread_count"] == 0


def test_dashboard_thread_unread_count_ignores_admin_reply(admin_api, client_api, client_user, django_admin_user):
    client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    chat = SupportChat.objects.get(client=client_user)
    create_support_message(chat=chat, sender=django_admin_user, content="Admin javobi")

    threads = admin_api.get(reverse("dashboard-support-threads"))

    assert threads.status_code == 200
    # Only the client's message is unread; the admin's own reply must not be counted.
    assert threads.data["data"]["results"][0]["unread_count"] == 1


def test_dashboard_threads_expose_status_and_sort_unread_first(admin_api, client_api, client_user, master_api, master):
    # Client thread keeps an unread message; master thread is read by the admin.
    client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    master_api.post(reverse("master-support"), {"message": "Buyurtma savoli"}, format="json")
    master_chat = SupportChat.objects.get(master=master)
    mark_chat_read_by_admin(master_chat)  # master thread now fully read (newer activity)

    response = admin_api.get(reverse("dashboard-support-threads"))

    assert response.status_code == 200
    results = response.data["data"]["results"]
    assert len(results) == 2
    # Unread thread floats to the top even though the master message is newer.
    assert results[0]["status"] == "unread"
    assert results[0]["has_unread"] is True
    assert results[0]["unread_count"] == 1
    assert results[0]["client"] is not None
    assert results[1]["status"] == "read"
    assert results[1]["has_unread"] is False
    assert results[1]["unread_count"] == 0


def test_admin_supportchat_orders_unread_first_and_renders_badge(django_admin_user, client_api, client_user, master_api, master):
    # Client chat stays unread; master chat is read (and thus updated most recently).
    client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    master_api.post(reverse("master-support"), {"message": "Buyurtma savoli"}, format="json")
    client_chat = SupportChat.objects.get(client=client_user)
    master_chat = SupportChat.objects.get(master=master)
    mark_chat_read_by_admin(master_chat)

    model_admin = SupportChatAdmin(SupportChat, admin_site)
    request = RequestFactory().get("/admin/support/supportchat/")
    request.user = django_admin_user
    ordered = list(model_admin.get_queryset(request).order_by(*model_admin.get_ordering(request)))

    # Unread chat is ordered before the read (but more recently updated) one.
    assert ordered.index(client_chat) < ordered.index(master_chat)

    unread_badge = model_admin.status_badge(client_chat)
    read_badge = model_admin.status_badge(master_chat)
    assert "Yangi" in unread_badge and "#dc3545" in unread_badge
    assert 'data-chat-id="%s"' % client_chat.id in unread_badge
    assert "O‘qilgan" in read_badge


def test_admin_supportchat_changelist_renders_with_badge(client, django_admin_user, client_api, client_user):
    client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    client.force_login(django_admin_user)

    response = client.get(reverse("admin:support_supportchat_changelist"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "support-status-badge" in content  # badge column is server-rendered
    assert "Yangi" in content
