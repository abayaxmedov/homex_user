from django.apps import AppConfig


class PaymeConfig(AppConfig):
    """App configuration for the Payme (Paycom) merchant integration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payme"
    verbose_name = "Payme"
