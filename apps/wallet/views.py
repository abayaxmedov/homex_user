from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, serializers

from apps.accounts.permissions import IsMaster
from apps.common.responses import success_response
from apps.common.views import EnvelopeMixin
from apps.wallet.models import MasterExpense, MasterWallet, WalletTransaction, WithdrawRequest
from apps.wallet.serializers import (
    MasterExpenseSerializer,
    MasterWalletSerializer,
    WalletTransactionSerializer,
    WithdrawRequestSerializer,
)


@extend_schema_view(get=extend_schema(tags=["Master Wallet"]))
class MasterWalletView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterWalletSerializer

    def get_object(self):
        wallet, _ = MasterWallet.objects.get_or_create(master=self.request.user)
        return wallet


@extend_schema_view(get=extend_schema(tags=["Master Wallet"]))
class WalletTransactionListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsMaster]
    serializer_class = WalletTransactionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return WalletTransaction.objects.none()
        return WalletTransaction.objects.filter(master=self.request.user)


@extend_schema_view(post=extend_schema(tags=["Master Wallet"]))
class WithdrawRequestCreateView(EnvelopeMixin, generics.CreateAPIView):
    permission_classes = [IsMaster]
    serializer_class = WithdrawRequestSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        amount = serializer.validated_data["amount"]
        wallet, _ = MasterWallet.objects.select_for_update().get_or_create(master=self.request.user)
        pending_withdraw = WithdrawRequest.objects.filter(
            master=self.request.user,
            status=WithdrawRequest.PENDING,
        ).aggregate(amount=Sum("amount"))["amount"] or Decimal("0.00")
        withdrawable = wallet.balance_cash - pending_withdraw
        if withdrawable < amount:
            raise serializers.ValidationError("Naqd balans yetarli emas")
        serializer.save(master=self.request.user)


def _income_between(master, start, end):
    return WalletTransaction.objects.filter(
        master=master,
        transaction_type=WalletTransaction.IN,
        created_at__gte=start,
        created_at__lt=end,
    ).aggregate(amount=Sum("amount"))["amount"] or Decimal("0.00")


def _change_percent(current, previous):
    if previous:
        return round(float((current - previous) / previous * 100), 1)
    return None  # o'tган davrda baza yo'q — foiz hisoblanmaydi


def _period_income_stats(master):
    """Bu hafta / bu oy kirimi (IN) + o'tган davrga nisbatan o'zgarish %.

    Kalendar hafta (dushanbadan) va oy (1-sanadan); joriy davr (start -> hozir)
    o'tган TO'LIQ davr bilan solishtiriladi.
    """
    today = timezone.localtime(timezone.now()).date()

    def _aware(d):
        return timezone.make_aware(datetime.combine(d, time.min))

    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    last_week_start = week_start - timedelta(days=7)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    now = timezone.now()

    week_now = _income_between(master, _aware(week_start), now)
    week_prev = _income_between(master, _aware(last_week_start), _aware(week_start))
    month_now = _income_between(master, _aware(month_start), now)
    month_prev = _income_between(master, _aware(last_month_start), _aware(month_start))
    return {
        "this_week": {"amount": week_now, "change_percent": _change_percent(week_now, week_prev)},
        "this_month": {"amount": month_now, "change_percent": _change_percent(month_now, month_prev)},
    }


@extend_schema(tags=["Master Wallet"])
class WalletStatsView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = WalletTransactionSerializer

    def get(self, request):
        wallet, _ = MasterWallet.objects.get_or_create(master=request.user)
        total = WalletTransaction.objects.filter(master=request.user, transaction_type=WalletTransaction.IN).aggregate(
            amount=Sum("amount")
        )["amount"] or 0
        recent = WalletTransaction.objects.filter(master=request.user)[:5]
        pending_withdraw = WithdrawRequest.objects.filter(
            master=request.user, status=WithdrawRequest.PENDING
        ).aggregate(amount=Sum("amount"))["amount"] or Decimal("0.00")
        withdrawable = max(wallet.balance_cash - pending_withdraw, Decimal("0.00"))
        period = _period_income_stats(request.user)
        return success_response(
            {
                "total_income": total,
                "this_week": period["this_week"],
                "this_month": period["this_month"],
                "balance_online": wallet.balance_online,
                "balance_cash": wallet.balance_cash,
                "total_balance": wallet.total_balance,
                "total_earned": wallet.total_earned,
                "total_withdrawn": wallet.total_withdrawn,
                "pending_withdraw": pending_withdraw,
                "withdrawable": withdrawable,
                "recent_transactions": WalletTransactionSerializer(recent, many=True).data,
            }
        )


@extend_schema_view(get=extend_schema(tags=["Master Expenses"]), post=extend_schema(tags=["Master Expenses"]))
class ExpenseListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterExpenseSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MasterExpense.objects.none()
        queryset = MasterExpense.objects.filter(master=self.request.user)
        date = self.request.query_params.get("date")
        return queryset.filter(date=date) if date else queryset

    def perform_create(self, serializer):
        serializer.save(master=self.request.user)


@extend_schema_view(get=extend_schema(tags=["Master Expenses"]), delete=extend_schema(tags=["Master Expenses"]))
class ExpenseDetailView(EnvelopeMixin, generics.RetrieveDestroyAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterExpenseSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MasterExpense.objects.none()
        return MasterExpense.objects.filter(master=self.request.user)
