from django.urls import path

from apps.orders import views


urlpatterns = [
    path("nearby/", views.NearbyMasterListView.as_view(), name="client-nearby-masters"),
]
