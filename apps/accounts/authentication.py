from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Client, Master, MasterApprovalStatus


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
        if not subject_id:
            raise exceptions.AuthenticationFailed("Invalid token role")
        if role == "admin":
            user_model = get_user_model()
            try:
                user = user_model.objects.get(id=subject_id, is_active=True, is_staff=True)
            except user_model.DoesNotExist as exc:
                raise exceptions.AuthenticationFailed("Admin user not found") from exc
            return user, token

        model = Master if role == "master" else Client if role == "client" else None
        if not model:
            raise exceptions.AuthenticationFailed("Invalid token role")
        lookup = {"id": subject_id, "is_active": True}
        if role == "master":
            lookup["approval_status"] = MasterApprovalStatus.APPROVED
        try:
            user = model.objects.get(**lookup)
        except model.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("User not found") from exc
        return user, token
