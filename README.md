# HomeX API

Django REST Framework backend for the HomeX client, master, web client, and admin integration flows.

## Notes

- API prefix: `/api/v1/`
- Schema: `/api/v1/schema/`
- Swagger UI: `/api/v1/docs/`
- ReDoc: `/api/v1/redoc/`

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

By default, settings fall back to SQLite when `DATABASE_URL` is not configured.

## Docker Deploy

```bash
cp .env.prod.example .env
# .env ichida DJANGO_SECRET_KEY, POSTGRES_PASSWORD, DJANGO_ALLOWED_HOSTS,
# CORS_ALLOWED_ORIGINS va CSRF_TRUSTED_ORIGINS qiymatlarini real domenlarga moslang.
# OTP SMS uchun (SMS_PROVIDER=eskiz): SMS_EMAIL, SMS_PASSWORD ni real Eskiz creds bilan,
# SMS_FROM ni Eskiz tasdiqlagan sender nickname bilan to'ldiring (bo'sh bo'lsa app boot
# bo'lmaydi — integrations.E001). SMS kerak bo'lmasa SMS_PROVIDER=stub qoldiring.
docker compose up -d --build
docker compose ps
```

Docker web service ASGI server bilan start bo'ladi:
`gunicorn config.asgi:application --worker-class uvicorn.workers.UvicornWorker`.
Shu sabab `/ws/...` WebSocket endpointlari Docker orqali ishlaydi.

Host Nginx proxy qilsa, `/ws/` uchun upgrade headerlar bo'lishi shart:

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

## Payme (Paycom) to'lov integratsiyasi

Merchant API (checkout redirect) integratsiyasi. Foydalanuvchi Payme ikonkasini bosadi →
app checkout havolasini oladi → Payme ilovasi ochiladi → to'lov qiladi → deep link orqali
HomeX'ga qaytadi. To'lovning **rost manbasi** — Payme'ning server-to-server
`PerformTransaction` chaqiruvi, redirect emas.

### Endpointlar

| URL | Kim uchun | Vazifa |
|-----|-----------|--------|
| `POST /api/v1/payme/` | **Payme kassa** | JSON-RPC merchant webhook — bu URL'ni Payme mutaxassisiga bering |
| `POST /api/v1/payme/checkout-url/<order_id>/` | Client (JWT) | Buyurtma uchun checkout havolasi + POST forma |
| `GET /api/v1/payme/order-status/<order_id>/` | Client (JWT) | To'lov holati (app poll qiladi) |

Webhook auth: `Authorization: Basic base64("Paycom:<key>")`. Barcha javoblar HTTP 200
JSON-RPC (global envelope'dan chetlab o'tadi). Summalar tiyinda (1 so'm = 100 tiyin).

### Env o'zgaruvchilari

`.env`ga qo'shing (`.env.example` / `.env.prod.example`da namuna bor):

```
PAYME_MERCHANT_ID=      # kassa merchant id
PAYME_KEY=              # prod kalit
PAYME_TEST_KEY=         # sandbox kalit
PAYME_TEST_MODE=true    # true => TEST_KEY qabul qilinadi, havolalar test.paycom.uz
PAYME_ACCOUNT_FIELD=order_id   # kassadagi account maydoni bilan BIR XIL bo'lishi shart
PAYME_CHECKOUT_URL=     # bo'sh => test/checkout.paycom.uz (test mode bo'yicha)
PAYME_RETURN_DEEPLINK=homex://payment/result
PAYME_CHECKOUT_LANG=uz
PAYME_ONE_TIME_PAYMENT=true
PAYME_ALLOWED_IPS=      # vergul bilan; bo'sh => IP tekshiruvi o'chiq
```

### Migration

```bash
python manage.py migrate
```

Qo'shilgan maydonlar: `Order.is_paid` / `Order.paid_at`; fiskal (`mxik`, `package_code`,
`vat_percent`) — `Service` va `WarehouseProduct` uchun. MXIK bo'sh bo'lsa fiskal `detail`
yuborilmaydi (allow-only). Fiskal chek uchun admin'da MXIK/IKPU kodlarini to'ldiring.

### Sandbox test (test.paycom.uz)

1. `PAYME_TEST_MODE=true`, `PAYME_TEST_KEY` ni kassadan oling; webhook URL: `https://<domen>/api/v1/payme/`.
2. **1-stsenariy:** CreateTransaction → tasdiqlanmagan tranzaksiyani CancelTransaction (state -1).
3. **2-stsenariy:** CreateTransaction → PerformTransaction → tasdiqlangan tranzaksiyani CancelTransaction (state -2).
4. Sandbox yashil bo'lgach: `PAYME_TEST_MODE=false`, `PAYME_KEY` (prod), `PAYME_CHECKOUT_URL=https://checkout.paycom.uz`.

## Firebase Cloud Messaging

Set `FCM_PROVIDER=firebase` and provide credentials with one of:

- `FIREBASE_CREDENTIALS_PATH=/absolute/path/to/service-account.json`
- `FIREBASE_CREDENTIALS_JSON='{"type":"service_account",...}'`
- `FIREBASE_CREDENTIALS_B64=<base64 encoded service account json>`

Keep service account files outside git. Client and master apps should register their FCM token with
`POST /api/v1/client/push/register/` or `POST /api/v1/master/push/register/`.
