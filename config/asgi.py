import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from apps.accounts.ws_auth import RoleJWTAuthMiddleware
from config.routing import websocket_urlpatterns


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": RoleJWTAuthMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
