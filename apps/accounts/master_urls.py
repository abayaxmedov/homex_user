from django.urls import include, path

from apps.accounts import views


auth_patterns = [
    path("register/", views.MasterRegisterView.as_view(), name="master-register"),
    path("login/", views.MasterLoginView.as_view(), name="master-login"),
    path("refresh/", views.MasterRefreshView.as_view(), name="master-refresh"),
    path("logout/", views.MasterLogoutView.as_view(), name="master-logout"),
    path("me/", views.MasterMeView.as_view(), name="master-me"),
    path("language/", views.MasterLanguageView.as_view(), name="master-language"),
    path("delete-account/", views.DeleteAccountView.as_view(), name="master-delete"),
]

urlpatterns = [
    path("auth/", include(auth_patterns)),
    path("home/", include("apps.orders.master_home_urls")),
    path("orders/", include("apps.orders.master_urls")),
    path("tracking/", include("apps.orders.master_tracking_urls")),
    path("wallet/", include("apps.wallet.master_wallet_urls")),
    path("expenses/", include("apps.wallet.master_expense_urls")),
    path("inventory/", include("apps.warehouse.master_urls")),
    path("reviews/", include("apps.orders.master_review_urls")),
    path("profile/", views.MasterProfileView.as_view(), name="master-profile"),
    path("profile/settings/", views.MasterSettingsView.as_view(), name="master-settings"),
    path("profile/", include("apps.profiles.master_urls")),
    path("push/register/", views.MasterPushRegisterView.as_view(), name="master-push-register"),
    path("notifications/", include("apps.notifications.master_urls")),
    path("support/", include("apps.support.master_urls")),
    path("privacy-policy/", include("apps.profiles.privacy_urls")),
]
