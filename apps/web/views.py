from django.db.models import Avg, Count, Sum
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny

from apps.accounts.models import Client, Master
from apps.common.responses import success_response
from apps.market.models import MarketCategory, MarketProduct
from apps.market.serializers import MarketCategoryListSerializer, MarketProductSerializer
from apps.orders.models import HomeBanner, Order, OrderStatus, Review
from apps.orders.views import DEFAULT_HOME_BANNERS
from apps.profiles.models import Tariff
from apps.profiles.serializers import TariffSerializer
from apps.services.models import Service, ServiceCategory
from apps.services.serializers import ServiceCategorySerializer, ServiceSerializer


def public_home_banners(request):
    banners = [banner.as_home_payload(request) for banner in HomeBanner.objects.filter(is_active=True)]
    return banners or DEFAULT_HOME_BANNERS


@extend_schema(tags=["Web App"], summary="Public web app home/bootstrap")
class WebHomeView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ServiceCategorySerializer

    def get(self, request):
        categories = ServiceCategory.objects.filter(is_active=True).prefetch_related("services__prices")
        featured_services = Service.objects.filter(is_active=True).select_related("category")[:12]
        market_categories = MarketCategory.objects.annotate(
            products_count=Count("marketproduct")
        ).order_by("name")[:12]
        market_products = (
            MarketProduct.objects.filter(is_active=True, is_moderated=True)
            .select_related("category", "seller")
            .prefetch_related("images")[:8]
        )
        tariffs = Tariff.objects.filter(is_active=True).prefetch_related("features")[:6]
        completed_orders = Order.objects.filter(status=OrderStatus.COMPLETED)
        data = {
            "hero": {
                "title": "HomeX",
                "subtitle": "Uy xizmatlari, ustalar va market bir joyda.",
                "primary_action": {"label": "Xizmat buyurtma qilish", "target": "client_order_create"},
                "secondary_action": {"label": "Usta bo'lib kirish", "target": "master_login"},
            },
            "banners": public_home_banners(request),
            "service_categories": ServiceCategorySerializer(categories, many=True, context={"request": request}).data,
            "featured_services": ServiceSerializer(featured_services, many=True, context={"request": request}).data,
            "tariffs": TariffSerializer(tariffs, many=True, context={"request": request}).data,
            "market": {
                "categories": MarketCategoryListSerializer(market_categories, many=True).data,
                "products": MarketProductSerializer(market_products, many=True, context={"request": request}).data,
            },
            "stats": {
                "clients_count": Client.objects.filter(is_active=True).count(),
                "masters_count": Master.objects.filter(is_active=True).count(),
                "completed_orders_count": completed_orders.count(),
                "average_rating": Review.objects.aggregate(avg=Avg("rating"))["avg"] or 0,
                "total_completed_amount": completed_orders.aggregate(total=Sum("total_amount"))["total"] or 0,
            },
            "navigation": [
                {"key": "services", "label": "Xizmatlar"},
                {"key": "market", "label": "Market"},
                {"key": "tariffs", "label": "Tariflar"},
                {"key": "support", "label": "Yordam"},
            ],
            "endpoints": {
                "client_auth": "/api/v1/client/auth/",
                "client_home": "/api/v1/client/home/",
                "client_services": "/api/v1/client/services/",
                "client_market": "/api/v1/client/market/",
                "master_auth": "/api/v1/master/auth/",
                "master_home": "/api/v1/master/home/",
            },
        }
        return success_response(data)


@extend_schema(tags=["Web App"], summary="Public web app meta")
class WebMetaView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ServiceCategorySerializer

    def get(self, request):
        return success_response(
            {
                "brand": {
                    "name": "HomeX",
                    "currency": "UZS",
                    "languages": [
                        {"code": "uz", "label": "O'zbekcha", "is_default": True},
                        {"code": "ru", "label": "Russkiy", "is_default": False},
                        {"code": "en", "label": "English", "is_default": False},
                    ],
                },
                "order_statuses": [
                    {"value": OrderStatus.NEW, "label": "Usta qidirilmoqda"},
                    {"value": OrderStatus.ACCEPTED, "label": "Usta yo'lda"},
                    {"value": OrderStatus.IN_PROGRESS, "label": "Usta ishlamoqda"},
                    {"value": OrderStatus.COMPLETED, "label": "Bajarildi"},
                    {"value": OrderStatus.CANCELLED, "label": "Bekor qilindi"},
                    {"value": OrderStatus.REJECTED, "label": "Rad etildi"},
                ],
                "market_conditions": [
                    {"value": "new", "label": "Yangi"},
                    {"value": "used", "label": "Ishlatilgan"},
                ],
                "app_links": {
                    "client_app": "/api/v1/client/app/bootstrap/",
                    "master_app": "/api/v1/master/app/bootstrap/",
                    "privacy_policy": "/api/v1/client/privacy-policy/",
                },
            }
        )
