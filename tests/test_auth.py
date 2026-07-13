from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Client, Master, MasterApprovalStatus, OTPRecord
from apps.accounts.serializers import SendOTPSerializer, VerifyOTPSerializer
from apps.accounts.tokens import issue_role_tokens


def test_dashboard_login_works_with_stray_admin_session(django_admin_user):
    # Reproduces the Swagger/browser case: already logged into /admin/ (session
    # cookie present). Login must not fail with a SessionAuthentication CSRF 403.
    api = APIClient()
    assert api.login(username="admin", password="admin")  # sets a session cookie

    response = api.post(
        reverse("dashboard-auth-login"),
        {"username": "admin", "password": "admin"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["data"]["access_token"]
    assert response.data["data"]["user"]["role"] == "admin"


def test_role_tokens_include_role(master, client_user):
    master_tokens = issue_role_tokens(master, "master")
    client_tokens = issue_role_tokens(client_user, "client")

    assert master_tokens["access_token"]
    assert client_tokens["access_token"]
    assert master_tokens["expires_in"] == 3 * 24 * 60 * 60
    assert client_tokens["expires_in"] == 3 * 24 * 60 * 60


def test_refresh_returns_new_access_and_refresh_tokens(client_user):
    api = APIClient()
    tokens = issue_role_tokens(client_user, "client")

    response = api.post(
        "/api/v1/client/auth/refresh/",
        {"refresh_token": tokens["refresh_token"]},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["data"]["access_token"]
    assert response.data["data"]["refresh_token"]
    assert response.data["data"]["expires_in"] == 3 * 24 * 60 * 60


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


def test_otp_cooldown_is_format_independent(db):
    # Every format variant of one number now collapses to a single cooldown key,
    # so the 180s cooldown can't be bypassed by reformatting the phone.
    first = SendOTPSerializer(data={"phone": "+998900000009"})
    assert first.is_valid(), first.errors
    first.save()

    variant = SendOTPSerializer(data={"phone": "998-900-000-009"})  # same handset
    assert not variant.is_valid()
    assert "phone" in variant.errors


def test_send_otp_endpoint_is_ip_throttled(db):
    # The unauthenticated, real-SMS endpoint must be rate-limited per IP (distinct
    # phones bypass the per-phone cooldown but not the per-IP burst throttle).
    cache.clear()
    api = APIClient()
    statuses = [
        api.post(reverse("client-send-otp"), {"phone": f"+99890010{n:04d}"}, format="json").status_code
        for n in range(7)
    ]
    assert 429 in statuses  # burst limit kicked in
    assert statuses.count(200) <= 5


def test_playmarket_test_otp_bypasses_send_endpoint_throttle(settings, db):
    settings.PLAYMARKET_TEST_PHONE = "+998900000000"
    settings.PLAYMARKET_TEST_OTP = "111111"
    cache.clear()
    api = APIClient()

    statuses = [
        api.post(reverse("client-send-otp"), {"phone": "+998900000000"}, format="json").status_code
        for _ in range(7)
    ]

    assert statuses == [200] * 7


def test_otp_blocks_after_five_wrong_attempts(settings, db):
    phone = "+998900000002"
    OTPRecord.objects.create(phone=phone, code="111111", expires_at=timezone.now() + timezone.timedelta(minutes=2))
    cache.set(f"otp:{phone}", {"code": "111111", "attempts": 0}, timeout=120)

    for _ in range(5):
        serializer = VerifyOTPSerializer(data={"phone": phone, "otp_code": "000000"})
        assert not serializer.is_valid()

    assert cache.get(f"otp:block:{phone}") is True


def test_playmarket_test_otp_does_not_expire_or_send_sms(settings, monkeypatch, db):
    settings.PLAYMARKET_TEST_PHONE = "+998900000000"
    settings.PLAYMARKET_TEST_OTP = "111111"
    sent = []
    monkeypatch.setattr("apps.accounts.serializers.send_otp_async", lambda phone, code: sent.append((phone, code)))

    first = SendOTPSerializer(data={"phone": "998-90-000-00-00"})
    assert first.is_valid(), first.errors
    assert first.save() == {"phone": "+998900000000", "expires_in": settings.OTP_TTL_SECONDS}

    second = SendOTPSerializer(data={"phone": "+998900000000"})
    assert second.is_valid(), second.errors
    second.save()

    verify = VerifyOTPSerializer(data={"phone": "+998900000000", "otp_code": "111111"})
    assert verify.is_valid(), verify.errors
    tokens = verify.save()

    assert sent == []
    assert OTPRecord.objects.filter(phone="+998900000000").count() == 0
    assert tokens["access_token"]
    assert tokens["client"]["phone"] == "+998900000000"


def test_playmarket_test_otp_rejects_wrong_code(settings, db):
    settings.PLAYMARKET_TEST_PHONE = "+998900000000"
    settings.PLAYMARKET_TEST_OTP = "111111"

    verify = VerifyOTPSerializer(data={"phone": "+998900000000", "otp_code": "000000"})

    assert not verify.is_valid()
    assert "OTP kodi noto'g'ri" in str(verify.errors)


def test_master_register_waits_for_admin_approval(db):
    api = APIClient()

    register = api.post(
        "/api/v1/master/auth/register/",
        {
            "first_name": "Ali",
            "last_name": "Karimov",
            "phone": "+998901110000",
            "specialization": "Konditsioner ustasi",
        },
        format="json",
    )
    blocked_login = api.post(
        "/api/v1/master/auth/login/",
        {"phone": "+998901110000", "password": "1234"},
        format="json",
    )
    master = Master.objects.get(phone="+998901110000")
    assert register.status_code == 201
    assert register.data["data"]["approval_status"] == MasterApprovalStatus.PENDING
    assert master.is_active is False
    assert master.password == ""
    assert blocked_login.status_code == 400
    assert "tasdig'ini kutmoqda" in str(blocked_login.data)

    master.approval_status = MasterApprovalStatus.APPROVED
    master.is_active = True
    master.password = "1234"
    master.save(update_fields=["approval_status", "is_active", "password", "updated_at"])
    approved_login = api.post(
        "/api/v1/master/auth/login/",
        {"phone": "+998901110000", "password": "1234"},
        format="json",
    )

    assert approved_login.status_code == 200
    assert approved_login.data["data"]["access_token"]


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


def test_client_delete_account_hard_deletes_user(client_api, client_user):
    response = client_api.delete("/api/v1/client/auth/delete-account/")

    assert response.status_code == 200
    assert not Client.objects.filter(id=client_user.id).exists()


def test_master_delete_account_hard_deletes_user(master_api, master):
    response = master_api.delete("/api/v1/master/auth/delete-account/")

    assert response.status_code == 200
    assert not Master.objects.filter(id=master.id).exists()
