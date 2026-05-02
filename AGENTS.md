# openweightsbackend

## Stack

- FastAPI + SQLModel + Alembic + pydantic-settings
- SQLite (dev) / PostgreSQL (prod)
- Custom JWT (HMAC-SHA256, no PyJWT/lib) + pbkdf2_sha256 passwords

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## Commands

- Run all tests: `pytest`
- Run single test: `pytest tests/test_file.py::test_name -v`
- Run server: `uvicorn app.main:app --reload`
- Migrations: `alembic upgrade head`
- Swagger: `http://127.0.0.1:8000/docs`
- Docker build: `docker build -t openweightsbackend .`

## Architecture

- `app/core/config.py` — pydantic-settings, loads `.env`
- `app/core/security.py` — custom token create/decode, PBKDF2 hashing
- `app/db/session.py` — SQLModel engine, SQLite vs PostgreSQL pool config
- `app/db/init_db.py` — `SQLModel.metadata.create_all(engine)` on startup
- `app/models/` — tables (`table=True`) + Pydantic schemas in same file
- `app/api/routes/` — one module per resource, registered in `router.py`
- `app/api/deps.py` — `get_current_user` / `get_optional_current_user`
- `app/services/` — persistence helpers, exercise access checks

## Testing

- `conftest.py` overrides `DATABASE_URL=sqlite://` (in-memory), creates tables per session, drops after
- Tests use `TestClient(app)` with dependency override of `get_session`
- `session` fixture yields a fresh SQLModel Session, tables created/dropped per fixture
- No lint/typecheck config in pyproject.toml — only pytest and coverage

## Database

- Schema also documented in `database.dbml`
- Alembic env reads `database_url` from pydantic-settings (not hardcoded)
- Custom constraint names: `uq_muscle_region_name_per_group`, `uq_exercise_name_per_user`
- Enum types: `laterality` (bilateral/unilateral), `side` (left/right/bilateral)
- Weight columns use `Numeric(6,2)` via `weight_field()` helper

## API patterns

- Auth: `HTTPBearer` header, token in `"sub"` is str(user_id)
- Pagination: `limit`/`offset` query params on list endpoints
- Cache: simple in-memory dict with TTL for muscle groups/regions
- 204 responses: `Response(status_code=204)`, no body
- Unique checks: email case-insensitive, exercise name per user
