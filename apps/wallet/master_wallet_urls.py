from django.urls import path

from apps.wallet import views


urlpatterns = [
    path("", views.MasterWalletView.as_view(), name="master-wallet"),
    path("transactions/", views.WalletTransactionListView.as_view(), name="master-wallet-transactions"),
    path("withdraw/", views.WithdrawRequestCreateView.as_view(), name="master-wallet-withdraw"),
    path("stats/", views.WalletStatsView.as_view(), name="master-wallet-stats"),
]
