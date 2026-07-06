from django.urls import reverse

from apps.wallet.models import MasterWallet, WalletTransaction, WithdrawRequest


def test_master_cash_handover_validates_balance(master_api, master):
    MasterWallet.objects.create(master=master, balance_cash=100000)

    ok = master_api.post(reverse("master-wallet-withdraw"), {"amount": "100000"}, format="json")
    too_much = master_api.post(reverse("master-wallet-withdraw"), {"amount": "200000"}, format="json")

    assert ok.status_code == 201
    assert too_much.status_code == 400
    assert WithdrawRequest.objects.filter(master=master).count() == 1


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
