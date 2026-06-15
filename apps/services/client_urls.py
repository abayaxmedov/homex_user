from django.urls import path

from apps.services import views


urlpatterns = [
    path("", views.ServiceCategoryListView.as_view(), name="client-services"),
    path("<uuid:pk>/prices/", views.ServicePriceView.as_view(), name="client-service-prices"),
]
