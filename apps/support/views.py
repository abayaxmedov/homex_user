from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.accounts.permissions import IsClient, IsMaster
from apps.common.views import EnvelopeMixin
from apps.support.models import SupportMessage
from apps.support.serializers import SupportMessageSerializer
from apps.support.services import broadcast_support_message


class BaseSupportListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    serializer_class = SupportMessageSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SupportMessage.objects.none()
        if getattr(self.request.user, "role", None) == "master":
            return SupportMessage.objects.filter(master=self.request.user)
        return SupportMessage.objects.filter(client=self.request.user)

    def perform_create(self, serializer):
        if getattr(self.request.user, "role", None) == "master":
            message = serializer.save(sender_role="master", master=self.request.user)
        else:
            message = serializer.save(sender_role="client", client=self.request.user)
        broadcast_support_message(message)


@extend_schema_view(
    get=extend_schema(
        tags=["Master Support"],
        summary="Master support messages",
        description="Support chat initial list. Realtime message uchun `/ws/master/support/` kanalidan foydalaning.",
    ),
    post=extend_schema(
        tags=["Master Support"],
        summary="Master support message yuborish",
        description="REST orqali support message yaratadi va WebSocket kanaliga realtime event yuboradi.",
    ),
)
class MasterSupportListCreateView(BaseSupportListCreateView):
    permission_classes = [IsMaster]


@extend_schema_view(
    get=extend_schema(
        tags=["Client Support"],
        summary="Client support messages",
        description="Support chat initial list. Realtime message uchun `/ws/client/support/` kanalidan foydalaning.",
    ),
    post=extend_schema(
        tags=["Client Support"],
        summary="Client support message yuborish",
        description="REST orqali support message yaratadi va WebSocket kanaliga realtime event yuboradi.",
    ),
)
class ClientSupportListCreateView(BaseSupportListCreateView):
    permission_classes = [IsClient]
