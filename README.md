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
- API requests are limited per client IP using an in-memory rolling window. Configure `API_RATE_LIMIT_ENABLED`, `API_RATE_LIMIT_REQUESTS` (default `100`), and `API_RATE_LIMIT_WINDOW_SECONDS` (default `60`). The limit applies to `/api/v1` requests, excludes CORS `OPTIONS` requests, and returns `429` with `Retry-After` (seconds) when exceeded. State is local to each process and is lost on restart.
- The key is `request.client.host` (the direct TCP peer) by default. Forwarded headers are ignored unless the peer IP is listed in comma-separated `API_RATE_LIMIT_TRUSTED_PROXIES`; then the first value of `API_RATE_LIMIT_PROXY_HEADER` (default `X-Forwarded-For`) is used. Keep the default empty behind Caddy unless Caddy is configured to overwrite the header and its fixed source IPs are explicitly trusted; arbitrary client-supplied forwarded headers must not be trusted.
- The global API limiter and the existing login brute-force limiter are independent layers: the global default is 100 requests per IP per 60-second rolling window, while login failures remain limited to 5 per IP per 15 minutes and successful login resets only the login counter.
