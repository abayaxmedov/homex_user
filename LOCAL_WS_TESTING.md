# Localda WebSocket test qilish (Docker)

## Nega 404 chiqardi?

`ws://127.0.0.1:8000/ws/...` ga ulanmoqchi bo'lganda **404** — bu server WebSocket'ni **WSGI** orqali qabul qilayotgani belgisi (masalan `manage.py runserver` — bu loyihada `daphne` o'rnatilmagani uchun oddiy WSGI dev-server ishga tushadi). WebSocket faqat **ASGI** (uvicorn/daphne) server ostida ishlaydi.

Production allaqachon to'g'ri: `gunicorn config.asgi:application --worker-class uvicorn.workers.UvicornWorker` (ASGI). Lekin localda ASGI server kerak edi.

## Yechim — alohida local Docker stack (production'ga tegilmagan)

Ikkita yangi fayl qo'shildi (production `docker-compose.yml` / `entrypoint.sh` / `settings.py` **o'zgarmagan**):
- `docker-compose.local.yml` — postgres + redis + web (uvicorn ASGI).
- `docker/entrypoint.local.sh` — migratsiya + `uvicorn config.asgi:application --reload`.

## Ishga tushirish

```bash
docker compose -f docker-compose.local.yml up --build
```

Bu ko'taradi:
- **db** (postgres, izolyatsiya qilingan volume)
- **redis** (channel layer — realtime broadcast uchun)
- **web** — `uvicorn config.asgi:application` (ASGI, WebSocket ishlaydi), kod mount qilingan (`--reload` bilan avtomatik qayta yuklanadi)

To'xtatish: `Ctrl+C`, yoki tozalash bilan: `docker compose -f docker-compose.local.yml down -v`.

## Test qilish

1. **Token oling** (REST orqali). Masalan client:
   - `POST http://localhost:8000/api/v1/client/auth/verify-otp/` (yoki loyihaga mos login) → `access_token`.
   - Dashboard: `POST http://localhost:8000/api/v1/dashboard/auth/login/` → `access_token`.

2. **WebSocket'ga ulaning** (Postman / Insomnia / Bruno):

   Client/master (native app usuli — **header**):
   ```
   ws://localhost:8000/ws/client/support/
   Header:  Authorization: Bearer <access_token>
   ```

   Dashboard (brauzer usuli — **query**):
   ```
   ws://localhost:8000/ws/dashboard/support/?token=<access_token>
   ws://localhost:8000/ws/dashboard/support/<chat_id>/?token=<access_token>
   ```

3. Ulanish ochilgach: client/master support socketiga `{"content":"salom"}` yuborsangiz — xabar yaratiladi va admin lobby / dashboard socketlariga realtime boradi.

## Muhim eslatmalar

- **404 o'rniga endi ishlaydi**, chunki uvicorn ASGI `/ws/` yo'llarini Channels routing orqali qabul qiladi.
- `REDIS_URL=redis://redis:6379/0` — channel layer Redis (prod bilan bir xil xatti-harakat, REST→WS broadcast va Celery ham ishlaydi).
- Redis kerak bo'lmasa, `docker-compose.local.yml` dagi `web.environment` ga `REDIS_URL: "locmem"` qo'ysangiz — Redis'siz, xotiradagi channel layer (bitta process uchun) ishlaydi. Lekin bir nechta process/Celery broadcast uchun Redis kerak.
- Docker ishlatmasdan test qilmoqchi bo'lsangiz: `pip install -r requirements.txt` + `REDIS_URL=locmem uvicorn config.asgi:application --reload` — bu ham ASGI, WebSocket ishlaydi. (`manage.py runserver` esa WSGI — WebSocket bermaydi.)
