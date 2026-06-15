from django.urls import path

from apps.notifications import views


urlpatterns = [
    path("", views.ClientNotificationListView.as_view(), name="client-notifications"),
    path("<uuid:pk>/read/", views.ClientNotificationReadView.as_view(), name="client-notification-read"),
    path("read-all/", views.ClientNotificationReadAllView.as_view(), name="client-notifications-read-all"),
]
