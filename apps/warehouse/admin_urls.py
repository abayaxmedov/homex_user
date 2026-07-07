from django.urls import path

from apps.warehouse import views


urlpatterns = [
    path("masters/<uuid:master_id>/inventory/", views.AdminMasterInventoryListView.as_view(), name="admin-master-inventory"),
    path(
        "masters/<uuid:master_id>/inventory/<uuid:item_id>/",
        views.AdminUpdateInventoryView.as_view(),
        name="admin-master-inventory-detail",
    ),
    path("warehouse/categories/", views.WarehouseCategoryListView.as_view(), name="admin-warehouse-categories"),
    path("warehouse/products/", views.WarehouseProductListView.as_view(), name="admin-warehouse-products"),
]
