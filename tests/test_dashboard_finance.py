from datetime import time
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Client
from apps.dashboard.models import DashboardCompanyExpense
from apps.orders.models import Order, OrderStatus
from apps.services.models import Service, ServiceCategory
from apps.wallet.models import MasterWallet, WalletTransaction, WithdrawRequest


def make_order(client, service, amount, status=OrderStatus.COMPLETED):
    # total_amount is not auto-computed on save(), so set it explicitly.
    return Order.objects.create(
        client=client,
        service=service,
        address_text="Toshkent, Chilonzor",
        lat="41.31000000",
        lng="69.24000000",
        scheduled_date=timezone.localdate(),
        scheduled_time=time(10, 0),
        status=status,
        service_fee=amount,
        total_amount=amount,
    )


def test_finance_summary_monthly_has_change_percent(admin_api, client_user, service):
    # 2 ta yakunlangan buyurtma (joriy oy) -> daromad, 1 ta kompaniya xarajati.
    make_order(client_user, service, 500_000)
    make_order(client_user, service, 300_000)
    make_order(client_user, service, 999_000, status=OrderStatus.NEW)  # income'ga kirmaydi
    DashboardCompanyExpense.objects.create(
        name="Ofis ijarasi", amount=200_000, date=timezone.localdate()
    )

    response = admin_api.get(reverse("dashboard-finance-summary"))
    assert response.status_code == 200
    data = response.data["data"]

    assert data["period"] == "month"
    # Har bir card qiymat + o'zgarish foizini qaytaradi (Figmadagi +12.5% uchun).
    assert data["income"]["value"] == 800_000
    assert data["expense"]["value"] == 200_000
    assert data["profit"]["value"] == 600_000
    for key in ("income", "expense", "profit"):
        assert "change_percent" in data[key]
        assert "change_direction" in data[key]
    assert data["orders_count"] == 2


def test_finance_summary_period_year(admin_api, client_user, service):
    make_order(client_user, service, 1_000_000)
    response = admin_api.get(reverse("dashboard-finance-summary"), {"period": "year"})
    assert response.status_code == 200
    data = response.data["data"]
    assert data["period"] == "year"
    assert data["income"]["value"] == 1_000_000


def test_income_by_service_returns_revenue_not_count(admin_api, client_user):
    cat = ServiceCategory.objects.create(name="Konditsioner", slug="konditsioner")
    kondi = Service.objects.create(category=cat, name="Konditsioner tozalash", base_price=100000)
    santex = Service.objects.create(category=cat, name="Santexnika", base_price=100000)
    # Konditsioner: 1 ta buyurtma 700k; Santexnika: 2 ta buyurtma 150k = 300k.
    make_order(client_user, kondi, 700_000)
    make_order(client_user, santex, 150_000)
    make_order(client_user, santex, 150_000)

    response = admin_api.get(reverse("dashboard-finance-income-by-service"))
    assert response.status_code == 200
    data = response.data["data"]

    assert data["total"] == 1_000_000
    # Daromad bo'yicha (SONi bo'yicha emas) tartiblanadi: Konditsioner birinchi.
    first = data["items"][0]
    assert first["service_name"] == "Konditsioner tozalash"
    assert first["income"] == 700_000
    assert first["percent"] == 70


def test_top_clients_ordered_by_spent(admin_api, service):
    big = Client.objects.create(phone="+998900000001", first_name="Katta", last_name="Mijoz")
    small = Client.objects.create(phone="+998900000002", first_name="Kichik", last_name="Mijoz")
    make_order(big, service, 900_000)
    make_order(big, service, 100_000)
    make_order(small, service, 50_000)

    response = admin_api.get(reverse("dashboard-finance-top-clients"))
    assert response.status_code == 200
    results = response.data["data"]["results"]

    assert results[0]["full_name"] == "Katta Mijoz"
    assert results[0]["orders_count"] == 2
    assert results[0]["total_spent"] == 1_000_000
    assert results[0]["rank"] == 1
    assert results[1]["full_name"] == "Kichik Mijoz"


def test_finance_export_returns_xlsx(admin_api, client_user, service):
    make_order(client_user, service, 500_000)
    response = admin_api.get(reverse("dashboard-finance-export"))
    assert response.status_code == 200
    assert (
        response["Content-Type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response["Content-Disposition"].startswith("attachment; filename=")
    # Haqiqiy xlsx (ZIP) fayl — "PK" magic bilan boshlanadi.
    assert response.getvalue()[:2] == b"PK"


def test_finance_report_bundles_all_sections(admin_api, client_user, service):
    make_order(client_user, service, 400_000)
    response = admin_api.get(reverse("dashboard-finance-report"))
    assert response.status_code == 200
    data = response.data["data"]
    assert set(data) >= {"summary", "chart", "income_by_service", "top_clients"}


def test_finance_endpoints_require_auth(api_client):
    for name in (
        "dashboard-finance-summary",
        "dashboard-finance-income-by-service",
        "dashboard-finance-top-clients",
        "dashboard-finance-export",
    ):
        assert api_client.get(reverse(name)).status_code in (401, 403)


def test_dashboard_withdraw_approval_debits_cash_balance(admin_api, master):
    """Approving a withdraw via the dashboard detail endpoint must actually debit
    the master's cash balance + record the OUT transaction (not just flip status)."""
    wallet, _ = MasterWallet.objects.get_or_create(master=master)
    wallet.balance_cash = Decimal("500000")
    wallet.balance_online = Decimal("100000")
    wallet.save(update_fields=["balance_cash", "balance_online"])
    assert wallet.total_balance == Decimal("600000")  # cash + online before withdraw
    wr = WithdrawRequest.objects.create(master=master, amount=Decimal("150000"))

    response = admin_api.patch(
        reverse("dashboard-withdraw-request-detail", args=[wr.id]),
        {"status": "approved"},
        format="json",
    )

    assert response.status_code == 200
    wr.refresh_from_db()
    wallet.refresh_from_db()
    assert wr.status == WithdrawRequest.APPROVED
    assert wallet.balance_cash == Decimal("350000")  # 500k - 150k debited
    assert wallet.balance_online == Decimal("100000")  # online untouched (cash-only withdraw)
    assert wallet.total_balance == Decimal("450000")  # umumiy balans ham kamaydi (350k + 100k)
    assert wallet.total_withdrawn == Decimal("150000")
    assert WalletTransaction.objects.filter(
        master=master, transaction_type=WalletTransaction.OUT, amount=Decimal("150000")
    ).exists()

    # Idempotent: re-PATCHing approved must not debit a second time.
    admin_api.patch(
        reverse("dashboard-withdraw-request-detail", args=[wr.id]),
        {"status": "approved"},
        format="json",
    )
    wallet.refresh_from_db()
    assert wallet.balance_cash == Decimal("350000")
    assert WalletTransaction.objects.filter(master=master, transaction_type=WalletTransaction.OUT).count() == 1


def test_dashboard_withdraw_reject_leaves_balance_untouched(admin_api, master):
    wallet, _ = MasterWallet.objects.get_or_create(master=master)
    wallet.balance_cash = Decimal("500000")
    wallet.save(update_fields=["balance_cash"])
    wr = WithdrawRequest.objects.create(master=master, amount=Decimal("150000"))

    response = admin_api.patch(
        reverse("dashboard-withdraw-request-detail", args=[wr.id]),
        {"status": "rejected", "admin_note": "Hujjat yetarli emas"},
        format="json",
    )

    assert response.status_code == 200
    wr.refresh_from_db()
    wallet.refresh_from_db()
    assert wr.status == WithdrawRequest.REJECTED
    assert wallet.balance_cash == Decimal("500000")  # unchanged
    assert not WalletTransaction.objects.filter(master=master).exists()
