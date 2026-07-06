from django.urls import path

from apps.profiles import views


urlpatterns = [
    path("", views.ClientDeviceListCreateView.as_view(), name="client-devices"),
    path("locations/", views.ClientDeviceLocationsView.as_view(), name="client-device-locations"),
    path("<uuid:pk>/", views.ClientDeviceDetailView.as_view(), name="client-device-detail"),
    path("<uuid:pk>/order/", views.ClientDeviceOrderView.as_view(), name="client-device-order"),
]
