from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.dashboard.models import DashboardStaffProfile


def test_dashboard_staff_create_supports_figma_modal_payload(admin_api):
    payload = {
        "full_name": "Jasur Karimov",
        "username": "jasur-operator-hx",
        "password": "demo12345",
        "profile": {
            "role": "operator",
            "phone": "(97) 106-10-05",
            "permissions": ["orders", "clients", "services", "tariffs"],
        },
    }

    response = admin_api.post(reverse("dashboard-staff"), payload, format="json")

    assert response.status_code == 201
    data = response.data["data"]
    assert data["full_name"] == "Jasur Karimov"
    assert data["username"] == "jasur-operator-hx"
    assert data["role"] == "operator"
    assert data["role_label"] == "Operator"
    assert data["phone"] == "(97) 106-10-05"
    assert data["permissions_count"] == 4
    assert data["permissions_display"] == "4-ta bo'lim"
    assert data["permissions_label"] == "Buyurtmalar, Mijozlar, Xizmat va Narxlar, Tariflar"
    assert data["avatar"] is None
    assert data["profile"]["permissions_count"] == 4

    user = get_user_model().objects.get(username="jasur-operator-hx")
    assert user.first_name == "Jasur"
    assert user.last_name == "Karimov"
    assert user.is_staff is True
    assert user.check_password("demo12345")


def test_dashboard_staff_create_supports_custom_role(admin_api):
    response = admin_api.post(
        reverse("dashboard-staff"),
        {
            "full_name": "Mavluda Mamatova",
            "username": "mavluda-sklad-hx",
            "password": "demo12345",
            "profile": {
                "role": "ombor-supervisor",
                "permissions": ["warehouse", "expenses", "services"],
            },
        },
        format="json",
    )

    assert response.status_code == 201
    data = response.data["data"]
    assert data["role"] == "ombor-supervisor"
    assert data["role_label"] == "Ombor-Supervisor"
    assert data["permissions_display"] == "3-ta bo'lim"
    assert data["permissions_label"] == "Ombor, Xarajatlar, Xizmat va Narxlar"


def test_dashboard_staff_list_returns_figma_table_fields(admin_api, django_admin_user):
    DashboardStaffProfile.objects.create(
        user=django_admin_user,
        role=DashboardStaffProfile.ADMIN,
        phone="(97) 106-10-05",
        permissions=[],
    )

    response = admin_api.get(reverse("dashboard-staff"), {"search": django_admin_user.username})

    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["username"] == django_admin_user.username
    assert row["role"] == "admin"
    assert row["role_label"] == "Admin"
    assert row["permissions_count"] is None
    assert row["permissions_display"] == "Barcha"
    assert row["permissions_label"] == "Barcha"
    assert row["phone"] == "(97) 106-10-05"
