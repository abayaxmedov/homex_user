from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OTPRecord
from apps.accounts.serializers import SendOTPSerializer, VerifyOTPSerializer
from apps.accounts.tokens import issue_role_tokens


def test_role_tokens_include_role(master, client_user):
    master_tokens = issue_role_tokens(master, "master")
    client_tokens = issue_role_tokens(client_user, "client")

    assert master_tokens["access_token"]
    assert client_tokens["access_token"]
    assert master_tokens["expires_in"] == 15 * 60
    assert client_tokens["expires_in"] == 60 * 60


def test_otp_send_and_verify_creates_client(db):
    serializer = SendOTPSerializer(data={"phone": "+998900000001"})
    assert serializer.is_valid(), serializer.errors
    result = serializer.save()
    code = cache.get("otp:+998900000001")["code"]

    verify = VerifyOTPSerializer(data={"phone": result["phone"], "otp_code": code})
    assert verify.is_valid(), verify.errors
    tokens = verify.save()

    assert tokens["access_token"]
    assert tokens["client"]["phone"] == "+998900000001"


def test_otp_blocks_after_five_wrong_attempts(settings, db):
    phone = "+998900000002"
    OTPRecord.objects.create(phone=phone, code="111111", expires_at=timezone.now() + timezone.timedelta(minutes=2))
    cache.set(f"otp:{phone}", {"code": "111111", "attempts": 0}, timeout=120)

    for _ in range(5):
        serializer = VerifyOTPSerializer(data={"phone": phone, "otp_code": "000000"})
        assert not serializer.is_valid()

    assert cache.get(f"otp:block:{phone}") is True


def test_bearer_token_takes_precedence_over_admin_session(django_admin_user, client_user):
    api = APIClient()
    assert api.login(username=django_admin_user.username, password="admin")
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_role_tokens(client_user, 'client')['access_token']}")

    response = api.patch(
        "/api/v1/client/auth/register/",
        {"first_name": "Ali", "last_name": "Valiyev", "language": "uz"},
        format="json",
    )

    assert response.status_code == 200
