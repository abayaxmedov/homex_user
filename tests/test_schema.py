from django.urls import reverse


def test_schema_endpoint_exists(client):
    response = client.get(reverse("schema"))
    assert response.status_code == 200


def test_schema_contains_frontend_friendly_docs(client):
    response = client.get(reverse("schema"))

    content = response.content.decode()
    assert "HomeX API" in content
    assert "Tez boshlash" in content
    assert "HTTP status kodlar" in content
    assert "Order statuslari" in content
    assert "current_tariff" in content
    assert "addresses_count" in content
    assert "Authorization: Bearer <access_token>" in content
    assert "/api/v1/master/auth/register/" in content
    assert "Master Auth" in content
    assert "approval_status" in content
