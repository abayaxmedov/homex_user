from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Client, Master


@database_sync_to_async
def get_role_user(token_value):
    try:
        token = AccessToken(token_value)
        role = token.get("role")
        model = Master if role == "master" else Client if role == "client" else None
        if not model:
            return None
        return model.objects.filter(id=token.get("sub"), is_active=True).first()
    except Exception:
        return None


class RoleJWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]
        scope["user"] = await get_role_user(token) if token else None
        return await self.app(scope, receive, send)
