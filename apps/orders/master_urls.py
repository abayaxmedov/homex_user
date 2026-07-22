from django.urls import path

from apps.orders import views


urlpatterns = [
    path("", views.MasterOrderListView.as_view(), name="master-orders"),
    path("<uuid:pk>/", views.MasterOrderDetailView.as_view(), name="master-order-detail"),
    path("<uuid:pk>/accept/", views.MasterOrderAcceptView.as_view(), name="master-order-accept"),
    path("<uuid:pk>/on-way/", views.MasterOrderOnWayView.as_view(), name="master-order-on-way"),
    path("<uuid:pk>/arrived/", views.MasterOrderStartView.as_view(), name="master-order-arrived"),
    path("<uuid:pk>/start/", views.MasterOrderStartView.as_view(), name="master-order-start"),
    path("<uuid:pk>/reject/", views.MasterOrderRejectView.as_view(), name="master-order-reject"),
    path("<uuid:pk>/complete/", views.MasterOrderCompleteView.as_view(), name="master-order-complete"),
    path("<uuid:pk>/confirm-cash/", views.MasterOrderConfirmCashView.as_view(), name="master-order-confirm-cash"),
    path("<uuid:pk>/receipt/confirm/", views.MasterOrderReceiptConfirmView.as_view(), name="master-order-receipt-confirm"),
    path("<uuid:pk>/track/", views.MasterOrderTrackView.as_view(), name="master-order-track"),
]
