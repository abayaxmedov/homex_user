from rest_framework import authentication, exceptions
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Client, Master


class RoleJWTAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword:
            return None
        try:
            token = AccessToken(parts[1])
        except TokenError as exc:
            raise exceptions.AuthenticationFailed("Invalid or expired token") from exc

        role = token.get("role")
        subject_id = token.get("sub")
        model = Master if role == "master" else Client if role == "client" else None
        if not model or not subject_id:
            raise exceptions.AuthenticationFailed("Invalid token role")
        try:
            user = model.objects.get(id=subject_id, is_active=True)
        except model.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("User not found") from exc
        return user, token
