import base64

from django.conf import settings

from apps.payme.const import Networks


class Initializer:
    """Builds Payme checkout redirect links (GET base64 URL + POST form).

    The ``amount`` passed here must already be in **tiyin** (1 so'm = 100 tiyin);
    the caller converts the order total. The account field name defaults to
    ``settings.PAYME_ACCOUNT_FIELD`` and must match the field configured in the
    Payme kassa.
    """

    def __init__(self, payme_id, fallback_id=None, is_test_mode=False, checkout_url=None):
        self.payme_id = payme_id
        self.fallback_id = fallback_id
        self.is_test_mode = is_test_mode
        self.checkout_url = checkout_url

    def _base_url(self) -> str:
        if self.checkout_url:
            return self.checkout_url.rstrip("/")
        if self.is_test_mode:
            return "https://test.paycom.uz"
        return "https://checkout.paycom.uz"

    def _account_field(self, account_field=None) -> str:
        return account_field or getattr(settings, "PAYME_ACCOUNT_FIELD", "order_id")

    def generate_pay_link(self, account_id, amount, return_url, lang="uz", account_field=None) -> str:
        """Return the GET checkout URL (base64-encoded params).

        Format::

            <checkout>/<base64("m=<id>;ac.<field>=<account_id>;a=<tiyin>;c=<return>;l=<lang>")>
        """
        account_field = self._account_field(account_field)
        params = (
            f"m={self.payme_id};ac.{account_field}={account_id};a={amount};c={return_url};l={lang}"
        )
        encoded = base64.b64encode(params.encode("utf-8")).decode("utf-8")
        return f"{self._base_url()}/{encoded}"

    def generate_post_params(self, account_id, amount, return_url, lang="uz", account_field=None) -> dict:
        """Return the action + hidden fields for a POST checkout form.

        Lets the client render a self-submitting HTML form as an alternative to
        the GET link (both open the same Payme checkout).
        """
        account_field = self._account_field(account_field)
        return {
            "action": f"{self._base_url()}/",
            "method": "POST",
            "fields": {
                "merchant": self.payme_id,
                "amount": amount,
                f"account[{account_field}]": account_id,
                "lang": lang,
                "callback": return_url,
            },
        }

    def generate_fallback_link(self, form_fields: dict = None) -> str:
        """Return the Payme fallback merchant URL."""
        result = f"https://payme.uz/fallback/merchant/?id={self.fallback_id}"
        if form_fields is not None:
            for key, value in form_fields.items():
                result += f"&{key}={value}"
        return result

    @staticmethod
    def api_url(is_test_mode: bool = False) -> str:
        """Return the server-to-server API base URL (for the receipts SDK)."""
        return Networks.TEST_NET.value if is_test_mode else Networks.PROD_NET.value
