import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Client, Master, MasterApprovalStatus


logger = logging.getLogger(__name__)


@database_sync_to_async
def get_role_user(token_value):
    try:
        token = AccessToken(token_value)
        role = token.get("role")
        subject_id = token.get("sub")
        # Dashboard uses role="admin" and a staff Django user.
        if role == "admin":
            user_model = get_user_model()
            return user_model.objects.filter(id=subject_id, is_active=True, is_staff=True).first()
        model = Master if role == "master" else Client if role == "client" else None
        if not model:
            return None
        queryset = model.objects.filter(id=subject_id, is_active=True)
        if role == "master":
            queryset = queryset.filter(approval_status=MasterApprovalStatus.APPROVED)
        return queryset.first()
    except Exception as exc:
        logger.warning(
            "WebSocket token authentication failed: %s",
            exc.__class__.__name__,
            exc_info=True,
        )
        return None


class RoleJWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = self._extract_token(scope)
        if token:
            scope["user"] = await get_role_user(token)
        elif "user" not in scope:
            scope["user"] = None
        return await self.app(scope, receive, send)

    @staticmethod
    def _extract_token(scope):
        """Return the JWT from the connection, or ``None``.

        Two transports are supported, header first:

        1. ``Authorization: Bearer <token>`` header — native clients, proxies.
        2. ``?token=<token>`` (or ``access_token``) query param — browsers can't
           set custom headers on ``new WebSocket()``, so the query string is the
           only way a browser client can authenticate. Prefer WSS so the token
           stays encrypted in transit; note it may still surface in proxy logs.
        """
        headers = dict(scope.get("headers") or [])
        auth_header = headers.get(b"authorization", b"").decode()
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]

        query = parse_qs(scope.get("query_string", b"").decode())
        values = query.get("token") or query.get("access_token")
        if values and values[0]:
            return values[0]
        return None
