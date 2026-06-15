from django.urls import path

from apps.profiles import views


urlpatterns = [
    path("", views.ClientAddressListCreateView.as_view(), name="client-addresses"),
    path("<uuid:pk>/", views.ClientAddressDetailView.as_view(), name="client-address-detail"),
]
