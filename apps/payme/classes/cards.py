from typing import Optional

from apps.payme.classes.http import HttpClient
from apps.payme.types.response import cards as response

ALLOWED_METHODS = {
    "cards.create": response.CardsCreateResponse,
    "cards.get_verify_code": response.GetVerifyResponse,
    "cards.verify": response.VerifyResponse,
    "cards.remove": response.RemoveResponse,
    "cards.check": response.CheckResponse,
}


class Cards:
    """Interface to the Payme card services (create/verify/check/remove)."""

    def __init__(self, url: str, payme_id: str):
        headers = {
            "X-Auth": payme_id,
            "Content-Type": "application/json",
        }
        self.http = HttpClient(url, headers)

    def create(self, number: str, expire: str, save: bool = False, timeout: int = 10) -> response.CardsCreateResponse:
        """Create a new card token."""
        method = "cards.create"
        params = {"card": {"number": number, "expire": expire}, "save": save}
        return self._post_request(method, params, timeout)

    def get_verify_code(self, token: str, timeout: int = 10) -> response.GetVerifyResponse:
        """Request an SMS verification code for a card token."""
        method = "cards.get_verify_code"
        params = {"token": token}
        return self._post_request(method, params, timeout)

    def verify(self, token: str, code: str, timeout: int = 10) -> response.VerifyResponse:
        """Verify a card token with the received code."""
        method = "cards.verify"
        params = {"token": token, "code": code}
        return self._post_request(method, params, timeout)

    def remove(self, token: str, timeout: int = 10) -> response.RemoveResponse:
        """Remove a card token."""
        method = "cards.remove"
        params = {"token": token}
        return self._post_request(method, params, timeout)

    def check(self, token: str, timeout: int = 10) -> response.CheckResponse:
        """Check the status of a card token."""
        method = "cards.check"
        params = {"token": token}
        return self._post_request(method, params, timeout)

    def _post_request(self, method: str, params: dict, timeout: int = 10):
        json = {"method": method, "params": params}
        dict_result = self.http.post(json, timeout)
        response_class = ALLOWED_METHODS[method]
        return response_class.from_dict(dict_result)

    @staticmethod
    def assert_and_print(condition: bool, success_message: str, test_case: Optional[str] = None):
        """Assertion helper for the manual SDK smoke test."""
        try:
            assert condition, "Assertion failed!"
            print(f"Success: {success_message}")
        except AssertionError as exc:
            error_message = (
                f"Test Case Failed: {test_case or 'Unknown Test Case'}\n"
                f"Error Details: {str(exc)}"
            )
            print(error_message)
            raise AssertionError(error_message) from exc
