from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken


def issue_role_tokens(subject, role):
    access_minutes = settings.MASTER_ACCESS_MINUTES if role == "master" else settings.CLIENT_ACCESS_MINUTES
    refresh_days = settings.MASTER_REFRESH_DAYS if role == "master" else settings.CLIENT_REFRESH_DAYS

    access = AccessToken()
    access.set_exp(from_time=timezone.now(), lifetime=timedelta(minutes=access_minutes))
    access["sub"] = str(subject.id)
    access["role"] = role
    access["phone"] = subject.phone

    refresh = RefreshToken()
    refresh.set_exp(from_time=timezone.now(), lifetime=timedelta(days=refresh_days))
    refresh["sub"] = str(subject.id)
    refresh["role"] = role

    return {
        "access_token": str(access),
        "refresh_token": str(refresh),
        "expires_in": access_minutes * 60,
    }
