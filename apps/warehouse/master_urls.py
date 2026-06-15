from django.urls import path

from apps.warehouse import views


urlpatterns = [
    path("", views.MasterInventoryListView.as_view(), name="master-inventory"),
    path("low-stock/", views.LowStockInventoryView.as_view(), name="master-inventory-low-stock"),
    path("<uuid:pk>/", views.MasterInventoryDetailView.as_view(), name="master-inventory-detail"),
    path("<uuid:pk>/use/", views.UseInventoryView.as_view(), name="master-inventory-use"),
]
