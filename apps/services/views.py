from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.accounts.permissions import IsClient
from apps.common.views import EnvelopeMixin
from apps.services.models import Service, ServiceCategory
from apps.services.serializers import ServiceCategorySerializer, ServiceSerializer


@extend_schema_view(get=extend_schema(tags=["Client Services"]))
class ServiceCategoryListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsClient]
    serializer_class = ServiceCategorySerializer
    pagination_class = None

    def get_queryset(self):
        return ServiceCategory.objects.filter(is_active=True).prefetch_related("services__prices")


@extend_schema_view(get=extend_schema(tags=["Client Services"]))
class ServicePriceView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [IsClient]
    serializer_class = ServiceSerializer

    def get_queryset(self):
        return Service.objects.filter(is_active=True).prefetch_related("prices")
