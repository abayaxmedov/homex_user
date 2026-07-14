from django.urls import reverse

from apps.wallet.models import MasterWallet, WalletTransaction, WithdrawRequest


def test_master_cash_handover_validates_balance(master_api, master):
    MasterWallet.objects.create(master=master, balance_cash=100000)

    ok = master_api.post(reverse("master-wallet-withdraw"), {"amount": "100000"}, format="json")
    too_much = master_api.post(reverse("master-wallet-withdraw"), {"amount": "200000"}, format="json")

    assert ok.status_code == 201
    assert too_much.status_code == 400
    assert WithdrawRequest.objects.filter(master=master).count() == 1


def test_master_cash_handover_rejects_non_positive_amount(master_api, master):
    MasterWallet.objects.create(master=master, balance_cash=100000)

    negative = master_api.post(reverse("master-wallet-withdraw"), {"amount": "-100000"}, format="json")
    zero = master_api.post(reverse("master-wallet-withdraw"), {"amount": "0"}, format="json")

    assert negative.status_code == 400
    assert zero.status_code == 400
    assert not WithdrawRequest.objects.filter(master=master).exists()


def test_master_cash_handover_reserves_pending_amount(master_api, master):
    MasterWallet.objects.create(master=master, balance_cash=100000)

    first = master_api.post(reverse("master-wallet-withdraw"), {"amount": "60000"}, format="json")
    second = master_api.post(reverse("master-wallet-withdraw"), {"amount": "50000"}, format="json")

    assert first.status_code == 201
    assert second.status_code == 400
    assert WithdrawRequest.objects.filter(master=master, status=WithdrawRequest.PENDING).count() == 1


def test_cash_handover_accept_zeroes_cash(master_api, master, admin_api):
    wallet = MasterWallet.objects.create(master=master, balance_cash=324000)
    master_api.post(reverse("master-wallet-withdraw"), {"amount": "324000"}, format="json")
    handover = WithdrawRequest.objects.get(master=master)

    accept = admin_api.post(reverse("dashboard-cash-handover-accept", args=[handover.id]))

    wallet.refresh_from_db()
    handover.refresh_from_db()
    assert accept.status_code == 200
    assert wallet.balance_cash == 0  # cash handed over -> balance emptied
    assert wallet.total_withdrawn == 324000
    assert handover.status == WithdrawRequest.APPROVED
    assert WalletTransaction.objects.filter(
        master=master, transaction_type=WalletTransaction.OUT, payment_method=WalletTransaction.CASH
    ).count() == 1
    # Accepting again is a no-op (idempotent).
    admin_api.post(reverse("dashboard-cash-handover-accept", args=[handover.id]))
    wallet.refresh_from_db()
    assert wallet.balance_cash == 0
    assert wallet.total_withdrawn == 324000


def test_cash_handover_accept_requires_current_cash_balance(master, admin_api):
    wallet = MasterWallet.objects.create(master=master, balance_cash=100000)
    handover = WithdrawRequest.objects.create(master=master, amount=150000, status=WithdrawRequest.PENDING)

    response = admin_api.post(reverse("dashboard-cash-handover-accept", args=[handover.id]))

    wallet.refresh_from_db()
    handover.refresh_from_db()
    assert response.status_code == 400
    assert wallet.balance_cash == 100000
    assert wallet.total_withdrawn == 0
    assert handover.status == WithdrawRequest.PENDING
    assert not WalletTransaction.objects.filter(master=master).exists()


def test_cash_handover_reject_keeps_cash(master_api, master, admin_api):
    wallet = MasterWallet.objects.create(master=master, balance_cash=324000)
    master_api.post(reverse("master-wallet-withdraw"), {"amount": "324000"}, format="json")
    handover = WithdrawRequest.objects.get(master=master)

    reject = admin_api.post(reverse("dashboard-cash-handover-reject", args=[handover.id]))

    wallet.refresh_from_db()
    handover.refresh_from_db()
    assert reject.status_code == 200
    assert wallet.balance_cash == 324000  # unchanged
    assert handover.status == WithdrawRequest.REJECTED
    assert not WalletTransaction.objects.filter(master=master).exists()


def test_cash_handover_accept_returns_enveloped_body_with_note(master_api, master, admin_api):
    MasterWallet.objects.create(master=master, balance_cash=488000)
    master_api.post(reverse("master-wallet-withdraw"), {"amount": "488000"}, format="json")
    handover = WithdrawRequest.objects.get(master=master)

    accept = admin_api.post(
        reverse("dashboard-cash-handover-accept", args=[handover.id]),
        {"note": "Naqd to'liq qabul qilindi"},
        format="json",
    )

    assert accept.status_code == 200
    # Enveloped response body: {success, message, data: {...cash handover...}}.
    assert accept.data["success"] is True
    data = accept.data["data"]
    assert data["id"] == str(handover.id)
    assert data["status"] == "approved"
    assert data["status_label"] == "Approved"
    assert data["admin_note"] == "Naqd to'liq qabul qilindi"  # request note persisted
    assert data["master_detail"]["id"] == str(master.id)


def test_cash_handover_accept_without_note_uses_default(master_api, master, admin_api):
    MasterWallet.objects.create(master=master, balance_cash=100000)
    master_api.post(reverse("master-wallet-withdraw"), {"amount": "100000"}, format="json")
    handover = WithdrawRequest.objects.get(master=master)

    accept = admin_api.post(reverse("dashboard-cash-handover-accept", args=[handover.id]))

    assert accept.status_code == 200
    assert accept.data["data"]["admin_note"] == "Naqd qabul qilindi"  # default note


def test_cash_handover_accept_rejects_too_long_note(master_api, master, admin_api):
    MasterWallet.objects.create(master=master, balance_cash=100000)
    master_api.post(reverse("master-wallet-withdraw"), {"amount": "100000"}, format="json")
    handover = WithdrawRequest.objects.get(master=master)

    response = admin_api.post(
        reverse("dashboard-cash-handover-accept", args=[handover.id]),
        {"note": "x" * 256},  # max_length=255
        format="json",
    )

    assert response.status_code == 400
    handover.refresh_from_db()
    assert handover.status == WithdrawRequest.PENDING  # invalid request -> no state change


def test_dashboard_cash_handover_list_defaults_to_pending(master, admin_api):
    WithdrawRequest.objects.create(master=master, amount=50000, status=WithdrawRequest.PENDING)
    WithdrawRequest.objects.create(master=master, amount=10000, status=WithdrawRequest.APPROVED)

    pending = admin_api.get(reverse("dashboard-cash-handovers"))
    approved = admin_api.get(reverse("dashboard-cash-handovers"), {"status": "approved"})

    assert pending.status_code == 200
    assert pending.data["count"] == 1
    row = pending.data["results"][0]
    assert row["status"] == "pending"
    assert row["master_detail"]["id"] == str(master.id)
    assert approved.data["count"] == 1


def test_wallet_stats_this_week_and_month_income(master_api, master):
    from datetime import datetime, time, timedelta
    from decimal import Decimal

    from django.utils import timezone

    today = timezone.localtime(timezone.now()).date()
    last_week_day = today - timedelta(days=today.weekday()) - timedelta(days=3)  # solidly last week

    # this-week income (created now)
    WalletTransaction.objects.create(
        master=master, transaction_type=WalletTransaction.IN, amount=Decimal("150000"),
        description="this week", payment_method=WalletTransaction.CASH,
    )
    # last-week income (backdated to compute the change %)
    prev = WalletTransaction.objects.create(
        master=master, transaction_type=WalletTransaction.IN, amount=Decimal("100000"),
        description="last week", payment_method=WalletTransaction.CASH,
    )
    WalletTransaction.objects.filter(id=prev.id).update(
        created_at=timezone.make_aware(datetime.combine(last_week_day, time(12, 0)))
    )

    data = master_api.get(reverse("master-wallet-stats")).data["data"]

    assert data["this_week"]["amount"] == Decimal("150000")           # only the current-week txn
    assert data["this_week"]["change_percent"] == 50.0                # (150k - 100k) / 100k * 100
    assert data["this_month"]["amount"] >= Decimal("150000")


def test_wallet_stats_change_percent_none_without_baseline(master_api, master):
    from decimal import Decimal

    WalletTransaction.objects.create(
        master=master, transaction_type=WalletTransaction.IN, amount=Decimal("70000"),
        description="only this week", payment_method=WalletTransaction.CASH,
    )
    data = master_api.get(reverse("master-wallet-stats")).data["data"]

    assert data["this_week"]["amount"] == Decimal("70000")
    assert data["this_week"]["change_percent"] is None  # o'tган hafta 0 -> baza yo'q
