from django.conf import settings
from django.core.checks import Error, register


@register()
def sms_provider_configured(app_configs, **kwargs):
    """Fail fast when SMS is 'enabled' but unconfigured.

    OTP send is fire-and-forget (the endpoint returns 200 even if the SMS never
    goes out), so a mis-set prod config is otherwise an INVISIBLE, total phone-login
    outage — every OTP request succeeds by HTTP while no user ever receives a code.
    This check turns that into a boot-time failure instead (migrate/startup runs
    system checks), so the container refuses to start rather than silently break login.
    """
    if getattr(settings, "SMS_PROVIDER", "stub").lower() != "eskiz":
        return []
    errors = []
    if not getattr(settings, "SMS_EMAIL", "") or not getattr(settings, "SMS_PASSWORD", ""):
        errors.append(
            Error(
                "SMS_PROVIDER=eskiz but SMS_EMAIL/SMS_PASSWORD is empty — OTP SMS would silently fail.",
                hint="Set real SMS_EMAIL and SMS_PASSWORD in .env, or set SMS_PROVIDER=stub.",
                id="integrations.E001",
            )
        )
    if not getattr(settings, "SMS_FROM", ""):
        errors.append(
            Error(
                "SMS_PROVIDER=eskiz but SMS_FROM (sender) is empty.",
                hint="Set SMS_FROM to the Eskiz-approved sender nickname (or 4546 for test).",
                id="integrations.E002",
            )
        )
    return errors
