from django.urls import path

from apps.notifications.consumers import ClientNotificationConsumer, MasterNotificationConsumer
from apps.orders.consumers import ClientTrackingConsumer, MasterTrackingConsumer
from apps.support.consumers import (
    AdminSupportChatConsumer,
    AdminSupportLobbyConsumer,
    ClientSupportConsumer,
    MasterSupportConsumer,
)


websocket_urlpatterns = [
    path("ws/master/tracking/", MasterTrackingConsumer.as_asgi()),
    path("ws/client/track/<uuid:order_id>/", ClientTrackingConsumer.as_asgi()),
    path("ws/master/notifications/", MasterNotificationConsumer.as_asgi()),
    path("ws/client/notifications/", ClientNotificationConsumer.as_asgi()),
    path("ws/master/support/", MasterSupportConsumer.as_asgi()),
    path("ws/client/support/", ClientSupportConsumer.as_asgi()),
    path("ws/support/<uuid:chat_id>/", AdminSupportChatConsumer.as_asgi()),
    path("ws/support/admin/lobby/", AdminSupportLobbyConsumer.as_asgi()),
]
