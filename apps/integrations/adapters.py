from dataclasses import dataclass


@dataclass
class StubResult:
    ok: bool = True
    provider: str = "stub"
    payload: dict | None = None


class SMSClient:
    def send_otp(self, phone, code):
        return StubResult(payload={"phone": phone, "code": code})


class PushClient:
    def send(self, token, title, body, data=None):
        return StubResult(payload={"token": token, "title": title, "body": body, "data": data or {}})


class PaymentClient:
    def create_payment(self, order, method):
        return StubResult(payload={"payment_url": f"https://payments.example.test/{order.id}?method={method}"})


class MapsClient:
    def config(self):
        return StubResult(payload={"provider": "google", "api_key": ""})
