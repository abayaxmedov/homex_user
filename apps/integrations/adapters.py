import base64
import json
from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings


@dataclass
class StubResult:
    ok: bool = True
    provider: str = "stub"
    payload: dict | None = None
    error: str = ""


class SMSClient:
    def send_otp(self, phone, code):
        return StubResult(payload={"phone": phone, "code": code})


def _stringify_fcm_data(data):
    payload = {}
    for key, value in (data or {}).items():
        if value is None:
            continue
        if isinstance(value, (dict, list, tuple)):
            payload[str(key)] = json.dumps(value, ensure_ascii=False)
        else:
            payload[str(key)] = str(value)
    return payload


def _firebase_credentials(credentials):
    credentials_json = getattr(settings, "FIREBASE_CREDENTIALS_JSON", "")
    credentials_b64 = getattr(settings, "FIREBASE_CREDENTIALS_B64", "")
    credentials_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", "")

    if credentials_json:
        return credentials.Certificate(json.loads(credentials_json))
    if credentials_b64:
        decoded = base64.b64decode(credentials_b64).decode("utf-8")
        return credentials.Certificate(json.loads(decoded))
    if credentials_path:
        return credentials.Certificate(credentials_path)
    return credentials.ApplicationDefault()


@lru_cache(maxsize=1)
def _firebase_app():
    from firebase_admin import credentials, get_app, initialize_app

    app_name = getattr(settings, "FIREBASE_APP_NAME", "[DEFAULT]")
    try:
        return get_app() if app_name == "[DEFAULT]" else get_app(app_name)
    except ValueError:
        credential = _firebase_credentials(credentials)
        if app_name == "[DEFAULT]":
            return initialize_app(credential)
        return initialize_app(credential, name=app_name)


class PushClient:
    def __init__(self, provider=None):
        self.provider = (provider or getattr(settings, "FCM_PROVIDER", "stub")).lower()

    def send(self, token, title, body, data=None):
        if self.provider != "firebase":
            return StubResult(
                provider=self.provider,
                payload={"token": token, "title": title, "body": body, "data": data or {}},
            )

        try:
            from firebase_admin import messaging

            message = messaging.Message(
                token=token,
                notification=messaging.Notification(title=title, body=body or ""),
                data=_stringify_fcm_data(data),
            )
            message_id = messaging.send(message, app=_firebase_app())
            return StubResult(
                provider="firebase",
                payload={"token": token, "message_id": message_id},
            )
        except Exception as exc:
            return StubResult(
                ok=False,
                provider="firebase",
                payload={"token": token, "title": title, "body": body, "data": data or {}},
                error=str(exc),
            )

    def send_many(self, tokens, title, body, data=None):
        results = [self.send(token, title, body, data=data) for token in tokens]
        success_count = sum(1 for result in results if result.ok)
        return StubResult(
            ok=success_count == len(results),
            provider=self.provider,
            payload={
                "success_count": success_count,
                "failure_count": len(results) - success_count,
                "responses": [
                    {
                        "ok": result.ok,
                        "provider": result.provider,
                        "payload": result.payload or {},
                        "error": result.error,
                    }
                    for result in results
                ],
            },
        )


class PaymentClient:
    def create_payment(self, order, method):
        return StubResult(payload={"payment_url": f"https://payments.example.test/{order.id}?method={method}"})


class MapsClient:
    def config(self):
        return StubResult(payload={"provider": "google", "api_key": ""})
