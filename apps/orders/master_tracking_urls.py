from django.urls import path

from apps.orders import views


urlpatterns = [
    path("location/", views.MasterLocationUpdateView.as_view(), name="master-location-update"),
]
