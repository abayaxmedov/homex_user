from typing import Optional, Union

from apps.payme.classes.http import HttpClient
from apps.payme.types.response import receipts as response

ALLOWED_METHODS = {
    "receipts.create": response.CreateResponse,
    "receipts.pay": response.PayResponse,
    "receipts.send": response.SendResponse,
    "receipts.cancel": response.CancelResponse,
    "receipts.check": response.CheckResponse,
    "receipts.get": response.GetResponse,
    "receipts.get_all": response.GetAllResponse,
}


class Receipts:
    """Interface to the Payme Receipts (server-initiated fiscal receipts)."""

    def __init__(self, payme_id: str, payme_key: str, url: str):
        headers = {
            "X-Auth": f"{payme_id}:{payme_key}",
            "Content-Type": "application/json",
        }
        self.http = HttpClient(url, headers)

    def create(
        self,
        account: dict,
        amount: Union[float, int],
        description: Optional[str] = None,
        detail: Optional[dict] = None,
        timeout: int = 10,
    ) -> response.CreateResponse:
        """Create a new receipt."""
        method = "receipts.create"
        params = {
            "amount": amount,
            "account": account,
            "description": description,
            "detail": detail,
        }
        return self._post_request(method, params, timeout)

    def pay(self, receipts_id: str, token: str, timeout: int = 10) -> response.PayResponse:
        """Pay a receipt using a card token."""
        method = "receipts.pay"
        params = {"id": receipts_id, "token": token}
        return self._post_request(method, params, timeout)

    def send(self, receipts_id: str, phone: str, timeout: int = 10) -> response.SendResponse:
        """Send a receipt to a phone number."""
        method = "receipts.send"
        params = {"id": receipts_id, "phone": phone}
        return self._post_request(method, params, timeout)

    def cancel(self, receipts_id: str, timeout: int = 10) -> response.CancelResponse:
        """Cancel a receipt."""
        method = "receipts.cancel"
        params = {"id": receipts_id}
        return self._post_request(method, params, timeout)

    def check(self, receipts_id: str, timeout: int = 10) -> response.CheckResponse:
        """Check a receipt's status."""
        method = "receipts.check"
        params = {"id": receipts_id}
        return self._post_request(method, params, timeout)

    def get(self, receipts_id: str, timeout: int = 10) -> response.GetResponse:
        """Get a single receipt's details."""
        method = "receipts.get"
        params = {"id": receipts_id}
        return self._post_request(method, params, timeout)

    def get_all(
        self, count: int, from_: int, to: int, offset: int, timeout: int = 10
    ) -> response.GetAllResponse:
        """Get all receipts for a time range."""
        method = "receipts.get_all"
        params = {"count": count, "from": from_, "to": to, "offset": offset}
        return self._post_request(method, params, timeout)

    def _post_request(self, method: str, params: dict, timeout: int = 10):
        json = {"method": method, "params": params}
        dict_result = self.http.post(json, timeout)
        response_class = ALLOWED_METHODS[method]
        return response_class.from_dict(dict_result)
