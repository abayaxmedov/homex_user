from django.urls import path

from apps.support import views


urlpatterns = [
    path("", views.ClientSupportListCreateView.as_view(), name="client-support"),
    path("messages/", views.ClientSupportListCreateView.as_view(), name="client-support-messages"),
]
