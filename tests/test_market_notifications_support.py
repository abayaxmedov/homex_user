from django.urls import reverse

from apps.market.models import MarketCategory, MarketFavorite, MarketOrder, MarketProduct
from apps.notifications.models import Notification
from apps.support.models import SupportMessage


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


def test_support_messages_are_scoped_by_role(client_api, master_api, client_user, master):
    client_response = client_api.post(reverse("client-support"), {"message": "Yordam kerak"}, format="json")
    master_response = master_api.post(reverse("master-support"), {"message": "Buyurtma savoli"}, format="json")

    assert client_response.status_code == 201
    assert master_response.status_code == 201
    assert SupportMessage.objects.filter(client=client_user, sender_role="client").exists()
    assert SupportMessage.objects.filter(master=master, sender_role="master").exists()
