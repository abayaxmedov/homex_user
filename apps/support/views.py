from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.response import Response

from apps.accounts.permissions import IsClient, IsMaster, IsStaffOrAdminUser
from apps.common.views import EnvelopeMixin
from apps.support.models import SupportChat, SupportMessage
from apps.support.serializers import SupportChatSerializer, SupportMessageSerializer
from apps.support.services import (
    broadcast_admin_update,
    broadcast_support_message,
    create_support_message,
    get_or_create_support_chat,
    mark_chat_read_by_admin,
    user_can_access_chat,
)


class BaseSupportListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    serializer_class = SupportMessageSerializer

    def get_chat(self):
        return get_or_create_support_chat(self.request.user)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SupportMessage.objects.none()
        chat = self.get_chat()
        if not chat:
            return SupportMessage.objects.none()
        return chat.messages.select_related("client", "master", "admin")

    def perform_create(self, serializer):
        chat = self.get_chat()
        message = create_support_message(
            chat=chat,
            sender=self.request.user,
            content=serializer.validated_data["message"],
            attachment=serializer.validated_data.get("attachment"),
        )
        broadcast_support_message(message)
        serializer.instance = message


class BaseSupportChatMeView(EnvelopeMixin, generics.RetrieveAPIView):
    serializer_class = SupportChatSerializer

    def get_object(self):
        return get_or_create_support_chat(self.request.user)


class AdminSupportChatListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsStaffOrAdminUser]
    serializer_class = SupportChatSerializer
    queryset = SupportChat.objects.select_related("client", "master").all()


class AdminSupportMessageListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsStaffOrAdminUser]
    serializer_class = SupportMessageSerializer

    def get_queryset(self):
        chat_id = self.request.query_params.get("chat")
        if not chat_id:
            return SupportMessage.objects.none()
        chat = get_object_or_404(SupportChat, pk=chat_id)
        if not user_can_access_chat(self.request.user, chat):
            return SupportMessage.objects.none()
        if mark_chat_read_by_admin(chat):
            broadcast_admin_update(chat)
        return chat.messages.select_related("client", "master", "admin")

    def list(self, request, *args, **kwargs):
        if not request.query_params.get("chat"):
            return Response({"detail": "chat query param required"}, status=status.HTTP_400_BAD_REQUEST)
        return super().list(request, *args, **kwargs)


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


class MasterSupportChatMeView(BaseSupportChatMeView):
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


class ClientSupportChatMeView(BaseSupportChatMeView):
    permission_classes = [IsClient]
