from django.urls import path

from apps.market import views


urlpatterns = [
    path("products/", views.MarketProductListView.as_view(), name="client-market-products"),
    path("products/<uuid:pk>/", views.MarketProductDetailView.as_view(), name="client-market-product-detail"),
    path("orders/", views.MarketOrderListCreateView.as_view(), name="client-market-orders"),
    path("favorites/", views.MarketFavoriteListView.as_view(), name="client-market-favorites"),
    path("favorites/toggle/", views.MarketFavoriteToggleView.as_view(), name="client-market-favorite-toggle"),
    path("listings/", views.ClientListingCreateView.as_view(), name="client-market-listing-create"),
    path("categories/", views.MarketCategoryListView.as_view(), name="client-market-categories")
]
