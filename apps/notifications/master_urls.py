from django.urls import path

from apps.notifications import views


urlpatterns = [
    path("", views.MasterNotificationListView.as_view(), name="master-notifications"),
    path("<uuid:pk>/read/", views.MasterNotificationReadView.as_view(), name="master-notification-read"),
    path("read-all/", views.MasterNotificationReadAllView.as_view(), name="master-notifications-read-all"),
]
