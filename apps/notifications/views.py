from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.accounts.permissions import IsClient, IsMaster
from apps.common.responses import success_response
from apps.common.views import EnvelopeMixin
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer
from apps.notifications.services import broadcast_notification, broadcast_notification_read_all


class NotificationListView(EnvelopeMixin, generics.ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        if getattr(self.request.user, "role", None) == "master":
            return Notification.objects.filter(master=self.request.user)
        return Notification.objects.filter(client=self.request.user)


class NotificationReadView(generics.GenericAPIView):
    serializer_class = NotificationSerializer

    def patch(self, request, pk):
        notification = self.get_queryset().get(pk=pk)
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        broadcast_notification(notification, event_type="notification.read")
        return success_response(NotificationSerializer(notification).data)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        if getattr(self.request.user, "role", None) == "master":
            return Notification.objects.filter(master=self.request.user)
        return Notification.objects.filter(client=self.request.user)


class NotificationReadAllView(generics.GenericAPIView):
    serializer_class = NotificationSerializer

    def patch(self, request):
        if getattr(request.user, "role", None) == "master":
            Notification.objects.filter(master=request.user).update(is_read=True)
            broadcast_notification_read_all("master", request.user.id)
        else:
            Notification.objects.filter(client=request.user).update(is_read=True)
            broadcast_notification_read_all("client", request.user.id)
        return success_response(message="All notifications marked as read")


MasterNotificationListView = extend_schema_view(
    get=extend_schema(
        tags=["Master Notifications"],
        summary="Master notifications list",
        description="Initial notification list uchun REST endpoint. Realtime update uchun `/ws/master/notifications/` kanaliga ulaning.",
    )
)(
    type("MasterNotificationListView", (NotificationListView,), {"permission_classes": [IsMaster]})
)
MasterNotificationReadView = extend_schema_view(
    patch=extend_schema(tags=["Master Notifications"], summary="Master notification read", description="Bitta notificationni read qiladi va realtime read event yuboradi.")
)(
    type("MasterNotificationReadView", (NotificationReadView,), {"permission_classes": [IsMaster]})
)
MasterNotificationReadAllView = extend_schema_view(
    patch=extend_schema(tags=["Master Notifications"], summary="Master notifications read all", description="Master notificationlarini hammasini read qiladi.")
)(
    type("MasterNotificationReadAllView", (NotificationReadAllView,), {"permission_classes": [IsMaster]})
)
ClientNotificationListView = extend_schema_view(
    get=extend_schema(
        tags=["Client Notifications"],
        summary="Client notifications list",
        description="Initial notification list uchun REST endpoint. Realtime update uchun `/ws/client/notifications/` kanaliga ulaning.",
    )
)(
    type("ClientNotificationListView", (NotificationListView,), {"permission_classes": [IsClient]})
)
ClientNotificationReadView = extend_schema_view(
    patch=extend_schema(tags=["Client Notifications"], summary="Client notification read", description="Bitta notificationni read qiladi va realtime read event yuboradi.")
)(
    type("ClientNotificationReadView", (NotificationReadView,), {"permission_classes": [IsClient]})
)
ClientNotificationReadAllView = extend_schema_view(
    patch=extend_schema(tags=["Client Notifications"], summary="Client notifications read all", description="Client notificationlarini hammasini read qiladi.")
)(
    type("ClientNotificationReadAllView", (NotificationReadAllView,), {"permission_classes": [IsClient]})
)
