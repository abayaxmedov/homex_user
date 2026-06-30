import secrets

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasHomexServiceToken(BasePermission):
    message = "Invalid HomeX service token."

    def has_permission(self, request, view):
        expected = getattr(settings, "HOMEX_INTERNAL_API_TOKEN", "")
        if not expected:
            return False

        provided = request.headers.get("X-Homex-Service-Token", "")
        authorization = request.headers.get("Authorization", "")
        if not provided and authorization.startswith("Service "):
            provided = authorization.removeprefix("Service ").strip()
        if not provided and authorization.startswith("Bearer "):
            provided = authorization.removeprefix("Bearer ").strip()

        return bool(provided and secrets.compare_digest(provided, expected))
