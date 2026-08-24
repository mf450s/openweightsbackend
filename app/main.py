from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.init_db import init_db
from app.middleware.rate_limit import InMemoryRateLimiter, IPRateLimitMiddleware

settings = get_settings()


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.method == "GET" and response.status_code == 200:
            if "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = "private, max-age=60"
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
api_rate_limiter = InMemoryRateLimiter(
    max_requests=settings.api_rate_limit_requests,
    window_seconds=settings.api_rate_limit_window_seconds,
)
trusted_proxy_ips = {
    value.strip()
    for value in settings.api_rate_limit_trusted_proxies.split(",")
    if value.strip()
}
app.add_middleware(
    IPRateLimitMiddleware,
    limiter=api_rate_limiter,
    api_prefix=settings.api_v1_prefix,
    enabled=settings.api_rate_limit_enabled,
    trusted_proxy_ips=trusted_proxy_ips,
    proxy_header=settings.api_rate_limit_proxy_header,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CacheControlMiddleware)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"message": settings.app_name}
