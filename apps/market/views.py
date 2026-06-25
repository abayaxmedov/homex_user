from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.accounts.permissions import IsClient
from apps.common.responses import success_response
from apps.common.views import EnvelopeMixin
from apps.market.models import MarketFavorite, MarketOrder, MarketProduct
from apps.market.serializers import MarketFavoriteSerializer, MarketOrderSerializer, MarketProductSerializer


@extend_schema_view(get=extend_schema(tags=["Client Market"]))
class MarketProductListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsClient]
    serializer_class = MarketProductSerializer

    def get_queryset(self):
        queryset = MarketProduct.objects.filter(is_active=True, is_moderated=True).select_related(
            "category", "seller"
        ).prefetch_related("images")
        category = self.request.query_params.get("category")
        search = self.request.query_params.get("search")
        condition = self.request.query_params.get("condition")
        min_price = self.request.query_params.get("min_price")
        max_price = self.request.query_params.get("max_price")
        if category:
            queryset = queryset.filter(category_id=category)
        if condition:
            queryset = queryset.filter(condition=condition)
        if search:
            queryset = queryset.filter(name__icontains=search)
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        return queryset


@extend_schema_view(get=extend_schema(tags=["Client Market"]))
class MarketProductDetailView(EnvelopeMixin, generics.RetrieveAPIView):
    permission_classes = [IsClient]
    serializer_class = MarketProductSerializer

    def get_queryset(self):
        return MarketProduct.objects.filter(is_active=True, is_moderated=True).select_related(
            "category", "seller"
        ).prefetch_related("images")


@extend_schema_view(get=extend_schema(tags=["Client Market"]), post=extend_schema(tags=["Client Market"]))
class MarketOrderListCreateView(EnvelopeMixin, generics.ListCreateAPIView):
    permission_classes = [IsClient]
    serializer_class = MarketOrderSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MarketOrder.objects.none()
        return MarketOrder.objects.filter(client=self.request.user).select_related("product")

    def perform_create(self, serializer):
        serializer.save(client=self.request.user)


@extend_schema_view(get=extend_schema(tags=["Client Market"]))
class MarketFavoriteListView(EnvelopeMixin, generics.ListAPIView):
    permission_classes = [IsClient]
    serializer_class = MarketFavoriteSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return MarketFavorite.objects.none()
        return MarketFavorite.objects.filter(client=self.request.user).select_related("product")


@extend_schema(tags=["Client Market"])
class MarketFavoriteToggleView(generics.GenericAPIView):
    permission_classes = [IsClient]
    serializer_class = MarketFavoriteSerializer

    def post(self, request):
        product = MarketProduct.objects.get(id=request.data.get("product"))
        favorite, created = MarketFavorite.objects.get_or_create(client=request.user, product=product)
        if not created:
            favorite.delete()
            return success_response({"favorited": False})
        return success_response({"favorited": True, "favorite": MarketFavoriteSerializer(favorite).data}, status=201)


@extend_schema_view(post=extend_schema(tags=["Client Market"]))
class ClientListingCreateView(EnvelopeMixin, generics.CreateAPIView):
    permission_classes = [IsClient]
    serializer_class = MarketProductSerializer

    def perform_create(self, serializer):
        serializer.save(seller=self.request.user, is_active=True, is_moderated=False)
