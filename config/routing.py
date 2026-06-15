from django.urls import path

from apps.orders.consumers import ClientTrackingConsumer, MasterTrackingConsumer
from apps.support.consumers import ClientSupportConsumer


websocket_urlpatterns = [
    path("ws/master/tracking/", MasterTrackingConsumer.as_asgi()),
    path("ws/client/track/<uuid:order_id>/", ClientTrackingConsumer.as_asgi()),
    path("ws/client/support/", ClientSupportConsumer.as_asgi()),
]
