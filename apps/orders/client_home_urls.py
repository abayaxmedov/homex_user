from django.urls import path

from apps.orders import views


urlpatterns = [
    path("", views.ClientHomeView.as_view(), name="client-home"),
    path("map-config/", views.ClientMapConfigView.as_view(), name="client-map-config"),
    path("recent-orders/", views.ClientRecentOrdersView.as_view(), name="client-recent-orders"),
]
