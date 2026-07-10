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

## Firebase Cloud Messaging

Set `FCM_PROVIDER=firebase` and provide credentials with one of:

- `FIREBASE_CREDENTIALS_PATH=/absolute/path/to/service-account.json`
- `FIREBASE_CREDENTIALS_JSON='{"type":"service_account",...}'`
- `FIREBASE_CREDENTIALS_B64=<base64 encoded service account json>`

Keep service account files outside git. Client and master apps should register their FCM token with
`POST /api/v1/client/push/register/` or `POST /api/v1/master/push/register/`.
