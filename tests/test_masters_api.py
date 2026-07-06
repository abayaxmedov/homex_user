from django.urls import reverse

from apps.accounts.models import Master, MasterApprovalStatus


def make_master(phone, first_name, specialization, **kwargs):
    defaults = {
        "phone": phone,
        "first_name": first_name,
        "specialization": specialization,
        "is_online": True,
        "is_active": True,
        "is_available": True,
    }
    defaults.update(kwargs)
    return Master.objects.create(**defaults)


def test_dashboard_masters_filter_by_specialization(admin_api):
    make_master("+998900000001", "Ali", "Santexnik")
    make_master("+998900000002", "Vali", "Elektrik")
    make_master("+998900000003", "Guli", "Santexnik-Payvandchi")

    all_masters = admin_api.get(reverse("dashboard-masters"))
    santexnik = admin_api.get(reverse("dashboard-masters"), {"specialization": "santexnik"})
    elektrik = admin_api.get(reverse("dashboard-masters"), {"specialization": "Elektrik"})
    multi = admin_api.get(reverse("dashboard-masters"), {"specialization": "elektrik, payvand"})

    assert all_masters.status_code == 200
    assert all_masters.data["count"] == 3
    # case-insensitive icontains
    assert {row["first_name"] for row in santexnik.data["results"]} == {"Ali", "Guli"}
    assert {row["first_name"] for row in elektrik.data["results"]} == {"Vali"}
    # comma-separated -> OR match
    assert {row["first_name"] for row in multi.data["results"]} == {"Vali", "Guli"}


def test_dashboard_masters_specializations_endpoint(admin_api):
    make_master("+998900000001", "Ali", "Santexnik")
    make_master("+998900000002", "Vali", "Elektrik")
    make_master("+998900000003", "Guli", "Santexnik")
    make_master("+998900000004", "Bek", "")  # empty specialization must be excluded

    response = admin_api.get(reverse("dashboard-masters-specializations"))

    assert response.status_code == 200
    results = response.data["data"]["results"]
    mapping = {row["specialization"]: row["count"] for row in results}
    assert mapping == {"Elektrik": 1, "Santexnik": 2}
    # sorted by specialization, no blank entry
    assert [row["specialization"] for row in results] == ["Elektrik", "Santexnik"]


def test_nearby_masters_filter_by_specialization(client_api):
    make_master("+998900000001", "Ali", "Santexnik", lat="41.30", lng="69.25")
    make_master("+998900000002", "Vali", "Elektrik", lat="41.30", lng="69.25")
    make_master("+998900000003", "Guli", "Santexnik-Payvandchi", lat="41.30", lng="69.25")
    # offline master must never appear regardless of specialization
    make_master("+998900000004", "Hasan", "Santexnik", is_online=False)

    santexnik = client_api.get(reverse("client-nearby-masters"), {"specialization": "santexnik"})
    multi = client_api.get(reverse("client-nearby-masters"), {"specialization": "elektrik,payvand"})

    assert santexnik.status_code == 200
    names = {row["full_name"] for row in santexnik.data["data"]}
    assert names == {"Ali", "Guli"}  # online santexnik masters only, offline Hasan excluded
    assert {row["full_name"] for row in multi.data["data"]} == {"Vali", "Guli"}


def test_dashboard_masters_applications_lists_pending_by_default(admin_api):
    make_master("+998900000001", "Ali", "Santexnik", approval_status=MasterApprovalStatus.PENDING)
    make_master("+998900000002", "Vali", "Elektrik", approval_status=MasterApprovalStatus.APPROVED)
    make_master("+998900000003", "Guli", "Payvandchi", approval_status=MasterApprovalStatus.REJECTED, is_active=False)

    pending = admin_api.get(reverse("dashboard-masters-applications"))
    rejected = admin_api.get(reverse("dashboard-masters-applications"), {"approval_status": "rejected"})
    approved = admin_api.get(reverse("dashboard-masters-applications"), {"approval_status": "approved"})
    bogus = admin_api.get(reverse("dashboard-masters-applications"), {"approval_status": "not-a-status"})

    assert pending.status_code == 200
    assert pending.data["count"] == 1
    row = pending.data["results"][0]
    assert row["first_name"] == "Ali"
    assert row["approval_status"] == "pending"
    assert row["approval_status_label"]  # display label present
    # approval_status override
    assert {r["first_name"] for r in rejected.data["results"]} == {"Guli"}
    assert {r["first_name"] for r in approved.data["results"]} == {"Vali"}
    # invalid value falls back to pending
    assert {r["first_name"] for r in bogus.data["results"]} == {"Ali"}


def test_dashboard_masters_applications_supports_search(admin_api):
    make_master("+998900000001", "Ali", "Santexnik", approval_status=MasterApprovalStatus.PENDING)
    make_master("+998900000002", "Bek", "Elektrik", approval_status=MasterApprovalStatus.PENDING)

    response = admin_api.get(reverse("dashboard-masters-applications"), {"search": "Bek"})

    assert response.status_code == 200
    assert {r["first_name"] for r in response.data["results"]} == {"Bek"}


def test_master_application_admin_lists_only_pending(client, django_admin_user):
    make_master("+998900000001", "Ali", "Santexnik", approval_status=MasterApprovalStatus.PENDING)
    make_master("+998900000002", "Vali", "Elektrik", approval_status=MasterApprovalStatus.APPROVED)
    client.force_login(django_admin_user)

    response = client.get(reverse("admin:accounts_masterapplication_changelist"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "+998900000001" in content  # pending master shown
    assert "+998900000002" not in content  # approved master excluded from the applications list


def test_dashboard_block_and_unblock_master(admin_api):
    master = make_master("+998900000009", "Blok", "Santexnik")

    block = admin_api.post(
        reverse("dashboard-master-block", args=[master.id]),
        {"is_blocked": True, "reason": "Qoidabuzarlik"},
        format="json",
    )
    master.refresh_from_db()

    assert block.status_code == 200
    assert master.is_blocked is True
    assert master.is_active is False  # blocked masters can no longer authenticate
    assert master.block_reason == "Qoidabuzarlik"
    assert master.blocked_at is not None

    blocked_list = admin_api.get(reverse("dashboard-masters-blocked"))
    status_filter = admin_api.get(reverse("dashboard-masters"), {"status": "blocked"})
    assert {r["id"] for r in blocked_list.data["results"]} == {str(master.id)}
    assert {r["id"] for r in status_filter.data["results"]} == {str(master.id)}

    unblock = admin_api.post(
        reverse("dashboard-master-block", args=[master.id]),
        {"is_blocked": False},
        format="json",
    )
    master.refresh_from_db()
    assert unblock.status_code == 200
    assert master.is_blocked is False
    assert master.is_active is True
    assert admin_api.get(reverse("dashboard-masters-blocked")).data["count"] == 0


def test_blocked_master_admin_lists_only_blocked(client, django_admin_user):
    make_master("+998900000001", "Blok", "Santexnik", is_blocked=True, is_active=False)
    make_master("+998900000002", "Faol", "Elektrik")
    client.force_login(django_admin_user)

    response = client.get(reverse("admin:accounts_blockedmaster_changelist"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "+998900000001" in content  # blocked master shown
    assert "+998900000002" not in content  # active master excluded
