from django.db.models import Sum
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

    def perform_create(self, serializer):
        wallet, _ = MasterWallet.objects.get_or_create(master=self.request.user)
        amount = serializer.validated_data["amount"]
        if wallet.balance_cash < amount:
            raise serializers.ValidationError("Naqd balans yetarli emas")
        serializer.save(master=self.request.user)


@extend_schema(tags=["Master Wallet"])
class WalletStatsView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = WalletTransactionSerializer

    def get(self, request):
        total = WalletTransaction.objects.filter(master=request.user, transaction_type=WalletTransaction.IN).aggregate(
            amount=Sum("amount")
        )["amount"] or 0
        return success_response({"total_income": total})


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
