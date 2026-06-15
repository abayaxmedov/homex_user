from django.urls import path

from apps.orders import views


urlpatterns = [
    path("stats/", views.MasterHomeStatsView.as_view(), name="master-home-stats"),
]
