# openweightsbackend

selfhosted backend for workouts

current db scheme needs to be updated in `database.dbml`.
planned stack:

| Tool | Use |
| --- | --- |
| FastAPI | API-Framework |
| SQLModel | ORM + Schemes |
| Uvicorn | ASGI-Server |
| Alembic | DB-Migrationen |
| PostgreSQL | proddb |
| SQLite | local dev |
| pytest | test |
| pythondotenv | envvars |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## API

- `GET /`
- `GET /api/v1/health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/users`
- `GET /api/v1/users/me`
- `PATCH /api/v1/users/me`
- `POST /api/v1/users/me/password`
- `DELETE /api/v1/users/me`
- `GET|PUT|PATCH /api/v1/users/me/settings`
- `GET|POST /api/v1/exercises`
- `GET|POST /api/v1/templates`
- `GET|PATCH|DELETE /api/v1/templates/{template_id}`
- `GET|POST /api/v1/templates/{template_id}/exercises`
- `PATCH|DELETE /api/v1/templates/{template_id}/exercises/{template_exercise_id}`
- `GET|POST /api/v1/sessions`

SwaggerUI: `http://127.0.0.1:8000/docs`

## Notes

- `DATABASE_URL` defaults to SQLite for local development.
- PostgreSQL is supported through the same `DATABASE_URL`.
- The SQLModel schema mirrors the current structure in `database.dbml`.
- Set `AUTH_SECRET_KEY` in production to a strong random value.
