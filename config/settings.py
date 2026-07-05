import os
from datetime import timedelta
from pathlib import Path

from django.urls import reverse_lazy

from apps.common.schema_docs import FRONTEND_GUIDE, OPENAPI_TAGS


BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-dev-secret")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "django_filters",
    "corsheaders",
    "channels",
    "apps.common",
    "apps.accounts",
    "apps.services",
    "apps.orders",
    "apps.warehouse",
    "apps.wallet",
    "apps.market",
    "apps.profiles",
    "apps.notifications",
    "apps.support",
    "apps.dashboard",
    "apps.integrations",
    "apps.internal_api",
    "apps.web",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres"):
    import urllib.parse

    parsed = urllib.parse.urlparse(DATABASE_URL)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username,
            "PASSWORD": parsed.password,
            "HOST": parsed.hostname,
            "PORT": parsed.port or 5432,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache"
        if REDIS_URL == "locmem"
        else "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "homex-cache" if REDIS_URL == "locmem" else REDIS_URL,
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
        if REDIS_URL == "locmem"
        else "channels_redis.core.RedisChannelLayer",
        "CONFIG": {}
        if REDIS_URL == "locmem"
        else {"hosts": [{"address": REDIS_URL, "socket_timeout": None}]},
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = os.getenv("MEDIA_URL", "/media/")
MEDIA_ROOT = os.getenv("MEDIA_ROOT", BASE_DIR / "media")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = []

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.RoleJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPageNumberPagination",
    "EXCEPTION_HANDLER": "apps.common.exceptions.homex_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "HomeX API",
    "DESCRIPTION": FRONTEND_GUIDE,
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "TAGS": OPENAPI_TAGS,
    "AUTHENTICATION_WHITELIST": [
        "apps.accounts.authentication.RoleJWTAuthentication",
    ],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "docExpansion": "none",
        "defaultModelsExpandDepth": 1,
        "defaultModelExpandDepth": 2,
        "tryItOutEnabled": True,
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=3),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=15),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()
]
CORS_ALLOW_ALL_ORIGINS = DEBUG and not CORS_ALLOWED_ORIGINS
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]

OTP_TTL_SECONDS = 120
OTP_SEND_COOLDOWN_SECONDS = 180
OTP_MAX_ATTEMPTS = 5
OTP_BLOCK_SECONDS = 900

ACCESS_TOKEN_DAYS = 3
REFRESH_TOKEN_DAYS = 15

MASTER_ACCESS_DAYS = ACCESS_TOKEN_DAYS
MASTER_REFRESH_DAYS = REFRESH_TOKEN_DAYS
CLIENT_ACCESS_DAYS = ACCESS_TOKEN_DAYS
CLIENT_REFRESH_DAYS = REFRESH_TOKEN_DAYS

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
HOMEX_INTERNAL_API_TOKEN = os.getenv("HOMEX_INTERNAL_API_TOKEN", "dev-internal-token" if DEBUG else "")

FCM_PROVIDER = os.getenv("FCM_PROVIDER", "stub").lower()
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
FIREBASE_CREDENTIALS_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON", "")
FIREBASE_CREDENTIALS_B64 = os.getenv("FIREBASE_CREDENTIALS_B64", "")
FIREBASE_APP_NAME = os.getenv("FIREBASE_APP_NAME", "[DEFAULT]")

UNFOLD = {
    "SITE_TITLE": "HomeX Admin",
    "SITE_HEADER": "HomeX Admin",
    "SITE_SUBHEADER": "Service operations panel",
    "SITE_URL": "/api/v1/docs/",
    "SITE_SYMBOL": "home_repair_service",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    "ENVIRONMENT": "apps.common.unfold.environment_callback",
    "ENVIRONMENT_TITLE_PREFIX": "apps.common.unfold.environment_title_prefix_callback",
    "BORDER_RADIUS": "8px",
    "COLORS": {
        "primary": {
            "50": "#fff7ed",
            "100": "#ffedd5",
            "200": "#fed7aa",
            "300": "#fdba74",
            "400": "#fb923c",
            "500": "#f97316",
            "600": "#ea580c",
            "700": "#c2410c",
            "800": "#9a3412",
            "900": "#7c2d12",
            "950": "#431407",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "command_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Operations",
                "separator": True,
                "collapsible": False,
                "items": [
                    {
                        "title": "Dashboard",
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                    {
                        "title": "Buyurtmalar",
                        "icon": "assignment",
                        "link": reverse_lazy("admin:orders_order_changelist"),
                        "badge": "apps.common.unfold.new_orders_badge",
                        "badge_variant": "warning",
                    },
                    {
                        "title": "Tracking",
                        "icon": "location_on",
                        "link": reverse_lazy("admin:orders_ordertracking_changelist"),
                    },
                    {
                        "title": "Notifications",
                        "icon": "notifications",
                        "link": reverse_lazy("admin:notifications_notification_changelist"),
                        "badge": "apps.common.unfold.unread_notifications_badge",
                        "badge_variant": "info",
                    },
                    {
                        "title": "Support chat",
                        "icon": "support_agent",
                        "link": reverse_lazy("admin:support_supportchat_changelist"),
                    },
                    {
                        "title": "Home banners",
                        "icon": "view_carousel",
                        "link": reverse_lazy("admin:orders_homebanner_changelist"),
                    },
                ],
            },
            {
                "title": "Users",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Mijozlar",
                        "icon": "person",
                        "link": reverse_lazy("admin:accounts_client_changelist"),
                    },
                    {
                        "title": "Ustalar",
                        "icon": "engineering",
                        "link": reverse_lazy("admin:accounts_master_changelist"),
                    },
                    {
                        "title": "Ariza qoldirgan ustalar",
                        "icon": "how_to_reg",
                        "link": reverse_lazy("admin:accounts_masterapplication_changelist"),
                        "badge": "apps.common.unfold.pending_masters_badge",
                        "badge_variant": "warning",
                    },
                    {
                        "title": "Bloklangan ustalar",
                        "icon": "block",
                        "link": reverse_lazy("admin:accounts_blockedmaster_changelist"),
                        "badge": "apps.common.unfold.blocked_masters_badge",
                        "badge_variant": "danger",
                    },
                    {
                        "title": "FCM devices",
                        "icon": "phonelink_ring",
                        "link": reverse_lazy("admin:accounts_fcmdevice_changelist"),
                    },
                    {
                        "title": "Admin users",
                        "icon": "admin_panel_settings",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                    },
                    {
                        "title": "Groups",
                        "icon": "groups",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
            {
                "title": "Services & Profiles",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Service categories",
                        "icon": "category",
                        "link": reverse_lazy("admin:services_servicecategory_changelist"),
                    },
                    {
                        "title": "Services",
                        "icon": "home_repair_service",
                        "link": reverse_lazy("admin:services_service_changelist"),
                    },
                    {
                        "title": "Narxlar",
                        "icon": "sell",
                        "link": reverse_lazy("admin:services_serviceprice_changelist"),
                    },
                    {
                        "title": "Manzillar",
                        "icon": "map",
                        "link": reverse_lazy("admin:profiles_clientaddress_changelist"),
                    },
                    {
                        "title": "Client devices",
                        "icon": "devices_other",
                        "link": reverse_lazy("admin:profiles_clientdevice_changelist"),
                    },
                    {
                        "title": "Tariflar",
                        "icon": "workspace_premium",
                        "link": reverse_lazy("admin:profiles_tariff_changelist"),
                    },
                ],
            },
            {
                "title": "Warehouse & Finance",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Sklad mahsulotlari",
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:warehouse_warehouseproduct_changelist"),
                        "badge": "apps.common.unfold.low_stock_badge",
                        "badge_variant": "danger",
                    },
                    {
                        "title": "Usta skladi",
                        "icon": "warehouse",
                        "link": reverse_lazy("admin:warehouse_masterinventory_changelist"),
                    },
                    {
                        "title": "Stock movements",
                        "icon": "sync_alt",
                        "link": reverse_lazy("admin:warehouse_stockmovement_changelist"),
                    },
                    {
                        "title": "Wallets",
                        "icon": "account_balance_wallet",
                        "link": reverse_lazy("admin:wallet_masterwallet_changelist"),
                    },
                    {
                        "title": "Transactions",
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:wallet_wallettransaction_changelist"),
                    },
                    {
                        "title": "Withdraw requests",
                        "icon": "payments",
                        "link": reverse_lazy("admin:wallet_withdrawrequest_changelist"),
                        "badge": "apps.common.unfold.pending_withdraw_badge",
                        "badge_variant": "warning",
                    },
                    {
                        "title": "Masterdan naqd pul qabul qilish",
                        "icon": "account_balance",
                        "link": reverse_lazy("admin:wallet_cashhandover_changelist"),
                        "badge": "apps.common.unfold.pending_cash_handover_badge",
                        "badge_variant": "warning",
                    },
                    {
                        "title": "Expenses",
                        "icon": "request_quote",
                        "link": reverse_lazy("admin:wallet_masterexpense_changelist"),
                    },
                ],
            },
            {
                "title": "Market & Content",
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": "Market products",
                        "icon": "storefront",
                        "link": reverse_lazy("admin:market_marketproduct_changelist"),
                    },
                    {
                        "title": "Market orders",
                        "icon": "shopping_cart",
                        "link": reverse_lazy("admin:market_marketorder_changelist"),
                    },
                    {
                        "title": "Market categories",
                        "icon": "sell",
                        "link": reverse_lazy("admin:market_marketcategory_changelist"),
                    },
                    {
                        "title": "Reviews",
                        "icon": "star",
                        "link": reverse_lazy("admin:orders_review_changelist"),
                    },
                    {
                        "title": "Certificates",
                        "icon": "verified",
                        "link": reverse_lazy("admin:profiles_mastercertificate_changelist"),
                    },
                    {
                        "title": "Documents",
                        "icon": "description",
                        "link": reverse_lazy("admin:profiles_masterdocument_changelist"),
                    },
                    {
                        "title": "Privacy policy",
                        "icon": "policy",
                        "link": reverse_lazy("admin:profiles_privacypolicy_changelist"),
                    },
                ],
            },
        ],
    },
}
