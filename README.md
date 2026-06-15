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
