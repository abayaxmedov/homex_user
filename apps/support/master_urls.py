from django.urls import path

from apps.support import views


urlpatterns = [
    path("", views.MasterSupportListCreateView.as_view(), name="master-support"),
    path("chat/", views.MasterSupportChatMeView.as_view(), name="master-support-chat"),
    path("messages/", views.MasterSupportListCreateView.as_view(), name="master-support-messages"),
]
