from fastapi import APIRouter

from app.api.routes import exercises, health, sessions, templates, users

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(exercises.router, prefix="/exercises", tags=["exercises"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
