from django.urls import path

from apps.support import views


urlpatterns = [
    path("", views.MasterSupportListCreateView.as_view(), name="master-support"),
]
