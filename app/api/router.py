from fastapi import APIRouter

from app.api.routes import auth, dashboard, database, exercises, health, sessions, splits, templates, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(exercises.router, prefix="/exercises", tags=["exercises"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(splits.router, prefix="/splits", tags=["splits"])
api_router.include_router(database.router, prefix="/database", tags=["database"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
