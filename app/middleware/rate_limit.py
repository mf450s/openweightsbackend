from collections import deque
from math import ceil
from threading import Lock
from time import monotonic
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


class InMemoryRateLimiter:
    """Thread-safe rolling-window request limiter keyed by client IP."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than zero")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be greater than zero")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, client_ip: str, now: float | None = None) -> tuple[bool, int, int]:
        """Return (allowed, remaining, retry_after_seconds)."""
        current = monotonic() if now is None else now
        with self._lock:
            timestamps = self._requests.setdefault(client_ip, deque())
            cutoff = current - self.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.max_requests:
                retry_after = max(1, ceil(timestamps[0] + self.window_seconds - current))
                return False, 0, retry_after

            timestamps.append(current)
            return True, self.max_requests - len(timestamps), 0

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()


def client_ip(
    request: Request,
    *,
    trusted_proxy_ips: set[str],
    proxy_header: str,
) -> str:
    """Use forwarded client IP only when the direct peer is explicitly trusted."""
    direct_ip = request.client.host if request.client else "unknown"
    if direct_ip not in trusted_proxy_ips:
        return direct_ip

    forwarded = request.headers.get(proxy_header)
    if forwarded:
        return forwarded.split(",", maxsplit=1)[0].strip() or direct_ip
    return direct_ip


class IPRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: Callable,
        *,
        limiter: InMemoryRateLimiter,
        api_prefix: str,
        enabled: bool = True,
        trusted_proxy_ips: set[str] | None = None,
        proxy_header: str = "X-Forwarded-For",
    ) -> None:
        super().__init__(app)
        self.limiter = limiter
        self.api_prefix = api_prefix.rstrip("/") or "/"
        self.enabled = enabled
        self.trusted_proxy_ips = trusted_proxy_ips or set()
        self.proxy_header = proxy_header

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if (
            not self.enabled
            or not request.url.path.startswith(self.api_prefix)
            or request.method == "OPTIONS"
        ):
            return await call_next(request)

        request_ip = client_ip(
            request,
            trusted_proxy_ips=self.trusted_proxy_ips,
            proxy_header=self.proxy_header,
        )
        allowed, remaining, retry_after = self.limiter.check(request_ip)
        headers = {
            "X-RateLimit-Limit": str(self.limiter.max_requests),
            "X-RateLimit-Remaining": str(remaining),
        }
        if not allowed:
            headers["Retry-After"] = str(retry_after)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers=headers,
            )

        response = await call_next(request)
        for name, value in headers.items():
            response.headers[name] = value
        return response
