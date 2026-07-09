from rest_framework.throttling import AnonRateThrottle


class OTPBurstThrottle(AnonRateThrottle):
    """Per-IP burst limit for the anonymous OTP-send endpoint.

    The per-phone cooldown only caps one number; it does NOT bound how many
    DISTINCT numbers a single source can spray real, billed SMS to. This throttle
    caps requests per source IP so an attacker can't enumerate numbers and drain
    the SMS balance / trip the aggregator. (Behind a proxy, ensure X-Forwarded-For
    is passed and DRF NUM_PROXIES is set so this keys on the real client IP.)
    """

    scope = "otp"


class OTPDailyThrottle(AnonRateThrottle):
    """Per-IP daily ceiling for the OTP-send endpoint (defense in depth)."""

    scope = "otp_day"
