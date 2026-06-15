from rest_framework import serializers

from apps.wallet.models import MasterExpense, MasterWallet, WalletTransaction, WithdrawRequest


class MasterWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterWallet
        fields = ("balance_online", "balance_cash", "total_earned", "total_withdrawn", "updated_at")


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ("id", "transaction_type", "amount", "description", "payment_method", "order", "created_at")


class WithdrawRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawRequest
        fields = ("id", "amount", "status", "admin_note", "created_at")
        read_only_fields = ("id", "status", "admin_note", "created_at")


class MasterExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterExpense
        fields = ("id", "purpose", "name", "amount", "date", "product_name", "price", "quantity", "created_at")
        read_only_fields = ("id", "created_at")
