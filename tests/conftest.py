import pytest
from rest_framework.test import APIClient

from apps.accounts.tokens import issue_role_tokens


@pytest.fixture(autouse=True)
def locmem_cache(settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"}}
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    settings.SECRET_KEY = "test-secret-key-with-enough-length-for-jwt"
    settings.SIMPLE_JWT["SIGNING_KEY"] = settings.SECRET_KEY


@pytest.fixture
def master(db):
    from apps.accounts.models import Master

    user = Master.objects.create(phone="+998901112233", first_name="Ali", last_name="Usta", password="1234")
    return user


@pytest.fixture
def client_user(db):
    from apps.accounts.models import Client

    return Client.objects.create(phone="+998909998877", first_name="Vali", last_name="Client")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def master_api(master):
    api_client = APIClient()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_role_tokens(master, 'master')['access_token']}")
    return api_client


@pytest.fixture
def client_api(client_user):
    api_client = APIClient()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_role_tokens(client_user, 'client')['access_token']}")
    return api_client


@pytest.fixture
def django_admin_user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="admin",
    )


@pytest.fixture
def admin_api(django_admin_user):
    api_client = APIClient()
    api_client.force_authenticate(user=django_admin_user)
    return api_client


@pytest.fixture
def service(db):
    from apps.services.models import Service, ServiceCategory, ServicePrice

    category = ServiceCategory.objects.create(name="Konditsioner", slug="konditsioner")
    service = Service.objects.create(category=category, name="Tozalash", base_price=100000)
    ServicePrice.objects.create(service=service, title="Standart", price=100000, unit="xizmat")
    return service
