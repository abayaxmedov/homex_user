import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.conf import settings
from django.core.asgi import get_asgi_application

# Initialize Django apps before importing anything that touches models/settings
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from apps.accounts.ws_auth import RoleJWTAuthMiddleware
from config.routing import websocket_urlpatterns

# In DEBUG (local uvicorn/docker) uvicorn doesn't serve static files like
# `runserver` does, so the admin/Unfold CSS+JS wouldn't load. Wrap the HTTP app
# so it serves /static/ directly. No-op in production (DEBUG=False) where nginx
# serves static.
http_app = django_asgi_app
if settings.DEBUG:
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

    http_app = ASGIStaticFilesHandler(django_asgi_app)

application = ProtocolTypeRouter(
    {
        "http": http_app,
        "websocket": AuthMiddlewareStack(RoleJWTAuthMiddleware(URLRouter(websocket_urlpatterns))),
    }
)
