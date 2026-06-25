from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, permissions

from apps.accounts.models import Client, FCMDevice, Master
from apps.accounts.permissions import IsClient, IsMaster
from apps.accounts.serializers import (
    ClientRegisterSerializer,
    ClientSerializer,
    FCMDeviceSerializer,
    LanguageSerializer,
    LogoutSerializer,
    MasterLoginSerializer,
    MasterProfileSerializer,
    RefreshSerializer,
    SendOTPSerializer,
    VerifyOTPSerializer,
)
from apps.common.responses import success_response
from apps.common.views import EnvelopeMixin


@extend_schema(tags=["Master Auth"])
class MasterLoginView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = MasterLoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.save())


@extend_schema(tags=["Master Auth"])
class MasterRefreshView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = RefreshSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.save())


@extend_schema(tags=["Master Auth"])
class MasterLogoutView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = LogoutSerializer

    def post(self, request):
        return success_response(message="Logged out")


@extend_schema(tags=["Master Auth"])
class MasterMeView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterProfileSerializer

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Master Auth"])
class MasterLanguageView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = LanguageSerializer

    def put(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.language = serializer.validated_data["language"]
        request.user.save(update_fields=["language"])
        return success_response({"language": request.user.language})


@extend_schema(tags=["Client Auth"])
class SendOTPView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = SendOTPSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.save())


@extend_schema(tags=["Client Auth"])
class VerifyOTPView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.save())


@extend_schema(tags=["Client Auth"])
class ClientRegisterView(EnvelopeMixin, generics.UpdateAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientRegisterSerializer

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Client Auth"])
class ClientRefreshView(MasterRefreshView):
    pass


@extend_schema(tags=["Client Auth"])
class ClientLogoutView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = LogoutSerializer

    def post(self, request):
        return success_response(message="Logged out")


@extend_schema(tags=["Client Auth"])
@extend_schema(tags=["Account"])
class DeleteAccountView(generics.GenericAPIView):
    serializer_class = LogoutSerializer

    def delete(self, request):
        request.user.is_active = False
        request.user.save(update_fields=["is_active"])
        return success_response(message="Delete request accepted")


@extend_schema(tags=["Client Profile"])
class ClientProfileView(EnvelopeMixin, generics.RetrieveUpdateAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientSerializer

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Master Profile"])
class MasterProfileView(EnvelopeMixin, generics.RetrieveUpdateAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterProfileSerializer

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Master Profile"])
class MasterSettingsView(generics.GenericAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterProfileSerializer

    def patch(self, request):
        allowed = {"notifications_enabled", "push_enabled", "is_online", "is_available"}
        for field in allowed:
            if field in request.data:
                setattr(request.user, field, request.data[field])
        request.user.save(update_fields=list(allowed))
        return success_response(MasterProfileSerializer(request.user).data)


@extend_schema(tags=["Client Profile"])
class ClientNotificationSettingsView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientSerializer

    def patch(self, request):
        for field in ("notifications_enabled", "push_enabled"):
            if field in request.data:
                setattr(request.user, field, request.data[field])
        request.user.save(update_fields=["notifications_enabled", "push_enabled"])
        return success_response(ClientSerializer(request.user).data)


@extend_schema_view(post=extend_schema(tags=["Master Push"]))
class MasterPushRegisterView(generics.CreateAPIView):
    permission_classes = [IsMaster]
    serializer_class = FCMDeviceSerializer

    def perform_create(self, serializer):
        serializer.save(role="master", master=self.request.user)


@extend_schema_view(post=extend_schema(tags=["Client Push"]))
class ClientPushRegisterView(generics.CreateAPIView):
    permission_classes = [IsClient]
    serializer_class = FCMDeviceSerializer

    def perform_create(self, serializer):
        serializer.save(role="client", client=self.request.user)
