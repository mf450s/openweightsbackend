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
