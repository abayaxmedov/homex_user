import base64
import json
import logging
import threading
from dataclasses import dataclass
from functools import lru_cache

import requests
from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)

ESKIZ_BASE_URL = "https://notify.eskiz.uz/api"
ESKIZ_TOKEN_CACHE_KEY = "eskiz:sms:token"
ESKIZ_TOKEN_TTL = 60 * 60 * 24 * 25  # ~25 kun (Eskiz tokeni ~30 kun yashaydi)


@dataclass
class StubResult:
    ok: bool = True
    provider: str = "stub"
    payload: dict | None = None
    error: str = ""


def _eskiz_phone(phone):
    # Eskiz 998XXXXXXXXX formatini kutadi (faqat raqamlar, '+' siz).
    return "".join(ch for ch in str(phone) if ch.isdigit())


def _mask_phone(phone):
    # Log faqat oxirgi 4 raqam — to'liq raqam (PII) prod loglarida saqlanmasin.
    digits = _eskiz_phone(phone)
    return ("*" * max(0, len(digits) - 4) + digits[-4:]) if digits else ""


class SMSClient:
    """OTP SMS'ni Eskiz (notify.eskiz.uz) orqali jo'natadi.

    SMS_PROVIDER != "eskiz" bo'lsa (dev/CI/testlar) no-op stub qaytaradi — hech narsa
    tarmoqqa chiqmaydi. Token cache'lanadi va 401 (muddati o'tган) bo'lsa bir marta
    qayta login qilinadi.
    """

    def __init__(self, provider=None):
        self.provider = (provider or getattr(settings, "SMS_PROVIDER", "stub")).lower()

    def send_otp(self, phone, code):
        message = f"Kodni hech kimga bermang! HomeX ilovasiga kirish uchun tasdiqlash kodi: {code}"
        if self.provider != "eskiz":
            return StubResult(provider=self.provider, payload={"phone": phone, "code": code, "message": message})
        try:
            return self._send_via_eskiz(phone, message)
        except Exception as exc:
            logger.exception("Eskiz SMS jo'natish muvaffaqiyatsiz phone=%s", _mask_phone(phone))
            return StubResult(ok=False, provider="eskiz", payload={"phone": phone}, error=str(exc))

    def _send_via_eskiz(self, phone, message, retry=True):
        response = requests.post(
            f"{ESKIZ_BASE_URL}/message/sms/send",
            json={
                "mobile_phone": _eskiz_phone(phone),
                "message": message,
                "from": getattr(settings, "SMS_FROM", "4546"),
            },
            headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"},
            timeout=(5, 10),  # (connect, read) — bound the worst case; no long hangs
        )
        if response.status_code == 401 and retry:
            cache.delete(ESKIZ_TOKEN_CACHE_KEY)  # token eskirgan — qayta login
            return self._send_via_eskiz(phone, message, retry=False)
        response.raise_for_status()
        body = response.json()
        # Eskiz ba'zan HTTP 200 bilan ham rad javobini qaytaradi (sender/shablon mos
        # kelmasa, balans, ...). Shuning uchun body statusini ham tekshiramiz.
        status = str(body.get("status", "")).lower()
        if body.get("id") or status in ("waiting", "success"):
            logger.info("Eskiz SMS qabul qilindi phone=%s id=%s status=%s", _mask_phone(phone), body.get("id"), status)
            return StubResult(provider="eskiz", payload=body)
        logger.warning("Eskiz SMS rad etildi phone=%s response=%s", _mask_phone(phone), body)
        return StubResult(ok=False, provider="eskiz", payload=body)

    def _token(self):
        token = cache.get(ESKIZ_TOKEN_CACHE_KEY)
        if token:
            return token
        response = requests.post(
            f"{ESKIZ_BASE_URL}/auth/login",
            json={"email": settings.SMS_EMAIL, "password": settings.SMS_PASSWORD},
            timeout=(5, 10),
        )
        response.raise_for_status()
        token = response.json()["data"]["token"]
        cache.set(ESKIZ_TOKEN_CACHE_KEY, token, ESKIZ_TOKEN_TTL)
        return token


def send_otp_async(phone, code):
    """Dispatch the OTP SMS OFF the request path.

    The Eskiz calls are synchronous HTTP; running them inline in the (sync) OTP view
    under a gunicorn UvicornWorker blocks the worker's shared thread-sensitive thread,
    so a slow/unreachable gateway would freeze the whole API. The stub/dev path is a
    no-op and runs inline (fast, deterministic for tests); the real Eskiz send runs in
    a fire-and-forget daemon thread.
    """
    client = SMSClient()
    if client.provider != "eskiz":
        return client.send_otp(phone, code)
    threading.Thread(target=client.send_otp, args=(phone, code), daemon=True, name="otp-sms").start()
    return None


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
