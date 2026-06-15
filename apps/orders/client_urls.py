from django.urls import path

from apps.orders import views


urlpatterns = [
    path("", views.ClientOrderListCreateView.as_view(), name="client-orders"),
    path("<uuid:pk>/", views.ClientOrderDetailView.as_view(), name="client-order-detail"),
    path("<uuid:pk>/cancel/", views.ClientOrderCancelView.as_view(), name="client-order-cancel"),
    path("<uuid:pk>/track/", views.ClientOrderTrackView.as_view(), name="client-order-track"),
    path("<uuid:pk>/rate/", views.ClientOrderRateView.as_view(), name="client-order-rate"),
    path("<uuid:pk>/pay/", views.ClientOrderPayView.as_view(), name="client-order-pay"),
]
