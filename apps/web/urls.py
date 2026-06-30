from django.urls import path

from .views import WebHomeView, WebMetaView


urlpatterns = [
    path("home/", WebHomeView.as_view(), name="web-home"),
    path("meta/", WebMetaView.as_view(), name="web-meta"),
]
