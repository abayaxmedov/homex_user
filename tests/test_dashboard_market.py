from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.market.models import MarketCategory, MarketProduct, MarketProductImage


def png_upload(name="p.png"):
    buffer = BytesIO()
    Image.new("RGB", (2, 2), "blue").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def test_dashboard_product_create_with_images_single_request(admin_api):
    category = MarketCategory.objects.create(name="Elektrik", slug="elektrik")

    response = admin_api.post(
        reverse("dashboard-market-products"),
        {
            "name": "Elektr kabel 20 metr",
            "description": "lorem ipsum",
            "price": "150000",
            "quantity": "12",
            "condition": "new",
            "category": str(category.id),
            "uploaded_images": [png_upload("a.png"), png_upload("b.png")],
        },
        format="multipart",
    )

    assert response.status_code == 201
    product = MarketProduct.objects.get(name="Elektr kabel 20 metr")
    # Details + images saved in ONE request (no separate image API call).
    assert product.category == category
    assert product.price == 150000
    assert MarketProductImage.objects.filter(product=product).count() == 2
    # Response uses the read representation (envelope + nested images).
    data = response.data["data"]
    assert data["name"] == "Elektr kabel 20 metr"
    assert len(data["images"]) == 2


def test_dashboard_product_create_without_images(admin_api):
    response = admin_api.post(
        reverse("dashboard-market-products"),
        {"name": "Rozetka", "price": "25000", "quantity": "5", "condition": "new"},
        format="multipart",
    )
    assert response.status_code == 201
    product = MarketProduct.objects.get(name="Rozetka")
    assert product.images.count() == 0


def test_dashboard_product_list_and_detail_are_enveloped(admin_api):
    product = MarketProduct.objects.create(name="Stabilizator", price=150000, quantity=12)

    listing = admin_api.get(reverse("dashboard-market-products"))
    detail = admin_api.get(reverse("dashboard-market-product-detail", args=[product.id]))

    assert listing.status_code == 200
    assert listing.data["success"] is True  # pagination envelope preserved
    assert {row["id"] for row in listing.data["results"]} == {str(product.id)}
    assert detail.status_code == 200
    assert detail.data["data"]["name"] == "Stabilizator"


def test_dashboard_product_update_adds_images(admin_api):
    product = MarketProduct.objects.create(name="Avtomat", price=150000, quantity=3)

    response = admin_api.patch(
        reverse("dashboard-market-product-detail", args=[product.id]),
        {"price": "180000", "uploaded_images": [png_upload("c.png")]},
        format="multipart",
    )

    assert response.status_code == 200
    product.refresh_from_db()
    assert product.price == 180000
    assert product.images.count() == 1


def test_dashboard_market_requires_staff(api_client):
    # Unauthenticated (non-staff) is rejected.
    response = api_client.get(reverse("dashboard-market-products"))
    assert response.status_code in (401, 403)
