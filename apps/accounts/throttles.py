from django.conf import settings
from rest_framework.throttling import AnonRateThrottle

from apps.common.phone import normalize_phone


def _is_playmarket_test_request(request):
    configured_phone = normalize_phone(getattr(settings, "PLAYMARKET_TEST_PHONE", ""))
    configured_otp = getattr(settings, "PLAYMARKET_TEST_OTP", "")
    request_phone = normalize_phone(getattr(request, "data", {}).get("phone"))
    return bool(configured_phone and configured_otp) and request_phone == configured_phone


class OTPBurstThrottle(AnonRateThrottle):
    """Per-IP burst limit for the anonymous OTP-send endpoint.

    The per-phone cooldown only caps one number; it does NOT bound how many
    DISTINCT numbers a single source can spray real, billed SMS to. This throttle
    caps requests per source IP so an attacker can't enumerate numbers and drain
    the SMS balance / trip the aggregator. (Behind a proxy, ensure X-Forwarded-For
    is passed and DRF NUM_PROXIES is set so this keys on the real client IP.)
    """

    scope = "otp"

    def allow_request(self, request, view):
        if _is_playmarket_test_request(request):
            return True
        return super().allow_request(request, view)


class OTPDailyThrottle(AnonRateThrottle):
    """Per-IP daily ceiling for the OTP-send endpoint (defense in depth)."""

    scope = "otp_day"

    def allow_request(self, request, view):
        if _is_playmarket_test_request(request):
            return True
        return super().allow_request(request, view)
