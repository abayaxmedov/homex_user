from django.urls import include, path

from apps.accounts import views


auth_patterns = [
    path("send-otp/", views.SendOTPView.as_view(), name="client-send-otp"),
    path("verify-otp/", views.VerifyOTPView.as_view(), name="client-verify-otp"),
    path("register/", views.ClientRegisterView.as_view(), name="client-register"),
    path("refresh/", views.ClientRefreshView.as_view(), name="client-refresh"),
    path("logout/", views.ClientLogoutView.as_view(), name="client-logout"),
    path("delete-account/", views.DeleteAccountView.as_view(), name="client-delete"),
]

urlpatterns = [
    path("auth/", include(auth_patterns)),
    path("home/", include("apps.orders.client_home_urls")),
    path("services/", include("apps.services.client_urls")),
    path("masters/", include("apps.orders.client_master_urls")),
    path("orders/", include("apps.orders.client_urls")),
    path("devices/", include("apps.profiles.client_device_urls")),
    path("market/", include("apps.market.client_urls")),
    path("addresses/", include("apps.profiles.client_address_urls")),
    path("tariffs/", include("apps.profiles.client_tariff_urls")),
    path("profile/", views.ClientProfileView.as_view(), name="client-profile"),
    path("profile/notifications/", views.ClientNotificationSettingsView.as_view(), name="client-notification-settings"),
    path("push/register/", views.ClientPushRegisterView.as_view(), name="client-push-register"),
    path("notifications/", include("apps.notifications.client_urls")),
    path("support/", include("apps.support.client_urls")),
    path("privacy-policy/", include("apps.profiles.privacy_urls")),
]
