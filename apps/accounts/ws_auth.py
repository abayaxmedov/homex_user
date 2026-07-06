import logging

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
        headers = dict(scope.get("headers") or [])
        auth_header = headers.get(b"authorization", b"").decode()
        parts = auth_header.split()
        token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else None
        if token:
            scope["user"] = await get_role_user(token)
        elif "user" not in scope:
            scope["user"] = None
        return await self.app(scope, receive, send)
