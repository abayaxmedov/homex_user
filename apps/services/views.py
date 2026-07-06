from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import AllowAny

from apps.accounts.permissions import IsClient
from apps.common.filters import filter_by_category
from apps.common.views import EnvelopeMixin
from apps.services.models import Service, ServiceCategory
from apps.services.serializers import ServiceCategorySerializer, ServiceSerializer


@extend_schema_view(
    get=extend_schema(
        tags=["Client Services"],
        parameters=[
            OpenApiParameter("category", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Bitta kategoriyani id yoki slug bo'yicha qaytaradi."),
            OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY, description="Kategoriya nomi/slug bo'yicha qidiruv."),
        ],
    )
)
class ServiceCategoryListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ServiceCategorySerializer
    pagination_class = None

    def get_queryset(self):
        queryset = ServiceCategory.objects.filter(is_active=True).prefetch_related("services__prices")
        queryset = filter_by_category(queryset, self.request, field="")
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(slug__icontains=search))
        return queryset


@extend_schema_view(get=extend_schema(tags=["Client Services"]))
class ServicePriceView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ServiceSerializer

    def get_queryset(self):
        return Service.objects.filter(is_active=True).prefetch_related("prices")
