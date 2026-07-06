from datetime import timedelta

from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import AllowAny

from apps.accounts.permissions import IsClient, IsMaster
from apps.accounts.serializers import ClientSerializer
from apps.common.responses import success_response
from apps.common.views import EnvelopeMixin
from apps.orders.models import Order
from apps.profiles.models import ClientAddress, ClientDevice, MasterCertificate, MasterDocument, PrivacyPolicy, Tariff
from apps.profiles.serializers import (
    ClientAddressSerializer,
    ClientDeviceSerializer,
    MasterCertificateSerializer,
    MasterDocumentSerializer,
    PrivacyPolicySerializer,
    TariffSerializer,
)


@extend_schema_view(
    get=extend_schema(
        tags=["Client Addresses"],
        summary="Client manzillari",
        description="Profile page `Manzillar` bo'limi uchun ro'yxat. Count `GET /client/profile/` ichida `addresses_count` bo'lib qaytadi.",
    ),
    post=extend_schema(
        tags=["Client Addresses"],
        summary="Yangi manzil qo'shish",
        description="Client yangi manzil qo'shadi. `is_default=true` yuborilsa oldingi default manzillar false qilinadi.",
        examples=[
            OpenApiExample(
                "Address create request",
                value={
                    "label": "Uy",
                    "address_text": "Chilonzor, Tashkent",
                    "lat": "41.30000000",
                    "lng": "69.25000000",
                    "is_default": True,
                },
                request_only=True,
            )
        ],
    ),
)
class ClientAddressListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientAddressSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ClientAddress.objects.none()
        return ClientAddress.objects.filter(client=self.request.user)

    def perform_create(self, serializer):
        if serializer.validated_data.get("is_default"):
            ClientAddress.objects.filter(client=self.request.user).update(is_default=False)
        serializer.save(client=self.request.user)


@extend_schema_view(
    get=extend_schema(tags=["Client Addresses"]),
    put=extend_schema(tags=["Client Addresses"]),
    patch=extend_schema(tags=["Client Addresses"]),
    delete=extend_schema(tags=["Client Addresses"]),
)
class ClientAddressDetailView(EnvelopeMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientAddressSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ClientAddress.objects.none()
        return ClientAddress.objects.filter(client=self.request.user)


@extend_schema_view(
    get=extend_schema(
        tags=["Client Devices"],
        summary="Client qurilmalari (location bo'yicha filter)",
        description="Client qurilmalari. `address_id` yoki `label` (Uy/Ish/...) bo'yicha location filtri qo'llanadi.",
        parameters=[
            OpenApiParameter("address_id", str, OpenApiParameter.QUERY, required=False, description="Location (ClientAddress) id bo'yicha filter."),
            OpenApiParameter("label", str, OpenApiParameter.QUERY, required=False, description="Location label bo'yicha filter (masalan Uy, Ish)."),
        ],
    ),
    post=extend_schema(tags=["Client Devices"]),
)
class ClientDeviceListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientDeviceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ClientDevice.objects.none()
        queryset = ClientDevice.objects.filter(client=self.request.user).select_related("address")
        address_id = self.request.query_params.get("address_id")
        if address_id:
            queryset = queryset.filter(address_id=address_id)
        label = self.request.query_params.get("label")
        if label:
            queryset = queryset.filter(address__label__icontains=label)
        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(client=self.request.user)


@extend_schema(
    tags=["Client Devices"],
    summary="Qurilma locationlari",
    description="Devices bo'limidagi location filtri uchun clientning manzillari va har biridagi qurilmalar soni.",
)
class ClientDeviceLocationsView(EnvelopeMixin, generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientAddressSerializer

    def get(self, request):
        addresses = (
            ClientAddress.objects.filter(client=request.user)
            .annotate(device_count=Count("devices"))
            .order_by("-is_default", "label")
        )
        results = [
            {
                "id": str(address.id),
                "label": address.label,
                "address_text": address.address_text,
                "lat": str(address.lat),
                "lng": str(address.lng),
                "is_default": address.is_default,
                "device_count": address.device_count,
            }
            for address in addresses
        ]
        return success_response({"count": len(results), "results": results})


@extend_schema_view(
    get=extend_schema(tags=["Client Devices"]),
    put=extend_schema(tags=["Client Devices"]),
    patch=extend_schema(tags=["Client Devices"]),
    delete=extend_schema(tags=["Client Devices"]),
)
class ClientDeviceDetailView(EnvelopeMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientDeviceSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ClientDevice.objects.none()
        return ClientDevice.objects.filter(client=self.request.user)


@extend_schema(
    tags=["Client Devices"],
    summary="Xizmat chaqirish (qurilmadan order)",
    description=(
        "Qurilma kartasidagi 'Xizmat chaqirish' tugmasi uchun. Order formasini oldindan to'ldirish uchun "
        "qurilma va manzil ma'lumotlarini qaytaradi. Order `POST /client/orders/` ga `device=<id>` bilan yuboriladi."
    ),
)
class ClientDeviceOrderView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = ClientDeviceSerializer

    def post(self, request, pk):
        device = get_object_or_404(ClientDevice, pk=pk, client=request.user)
        address = device.address
        return success_response(
            {
                "device": ClientDeviceSerializer(device, context={"request": request}).data,
                "order_endpoint": "/api/v1/client/orders/",
                "prefill": {
                    "device": str(device.id),
                    "address": str(address.id) if address else None,
                    "address_text": address.address_text if address else None,
                    "lat": str(address.lat) if address else None,
                    "lng": str(address.lng) if address else None,
                },
            }
        )


@extend_schema_view(
    get=extend_schema(
        tags=["Client Tariffs"],
        summary="Tariflar ro'yxati",
        description="Profile page `Tariflar` bo'limi uchun active tariflar. Client profile response `current_tariff` ID emas, nom qaytaradi.",
    )
)
class TariffListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsClient]
    serializer_class = TariffSerializer
    pagination_class = None

    def get_queryset(self):
        return Tariff.objects.filter(is_active=True)


@extend_schema(
    tags=["Client Tariffs"],
    summary="Tarifga ulanish",
    description="Client tanlangan tarifga ulanadi. Response ichida tarif detail va yangilangan client profile qaytadi.",
    examples=[OpenApiExample("Subscribe request", value={"tariff_id": "tariff_uuid"}, request_only=True)],
)
class TariffSubscribeView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = TariffSerializer

    def post(self, request):
        tariff = Tariff.objects.get(id=request.data.get("tariff_id"), is_active=True)
        request.user.current_tariff = tariff
        request.user.tariff_expires_at = timezone.now() + timedelta(days=tariff.duration_days)
        request.user.save(update_fields=["current_tariff", "tariff_expires_at"])
        return success_response({"tariff": TariffSerializer(tariff).data, "client": ClientSerializer(request.user).data})


@extend_schema_view(get=extend_schema(tags=["Master Profile"]), post=extend_schema(tags=["Master Profile"]))
class MasterCertificateListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterCertificateSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MasterCertificate.objects.none()
        return MasterCertificate.objects.filter(master=self.request.user)

    def perform_create(self, serializer):
        serializer.save(master=self.request.user)


@extend_schema_view(delete=extend_schema(tags=["Master Profile"]))
class MasterCertificateDeleteView(EnvelopeMixin, generics.DestroyAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterCertificateSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MasterCertificate.objects.none()
        return MasterCertificate.objects.filter(master=self.request.user)


@extend_schema_view(get=extend_schema(tags=["Master Profile"]), post=extend_schema(tags=["Master Profile"]))
class MasterDocumentListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    permission_classes = [IsMaster]
    serializer_class = MasterDocumentSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MasterDocument.objects.none()
        return MasterDocument.objects.filter(master=self.request.user)

    def perform_create(self, serializer):
        serializer.save(master=self.request.user)


@extend_schema_view(get=extend_schema(tags=["Privacy Policy"]))
class PrivacyPolicyView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = []
    authentication_classes = []
    serializer_class = PrivacyPolicySerializer

    def get_object(self):
        return PrivacyPolicy.objects.order_by("-updated_at").first()
