from django.urls import reverse


def test_schema_endpoint_exists(client):
    response = client.get(reverse("schema"))
    assert response.status_code == 200
