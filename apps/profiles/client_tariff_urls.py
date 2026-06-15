from django.urls import path

from apps.profiles import views


urlpatterns = [
    path("", views.TariffListView.as_view(), name="client-tariffs"),
    path("subscribe/", views.TariffSubscribeView.as_view(), name="client-tariff-subscribe"),
]
