import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application

# Initialize Django apps before importing anything that touches models/settings
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from apps.accounts.ws_auth import RoleJWTAuthMiddleware
from config.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": RoleJWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
