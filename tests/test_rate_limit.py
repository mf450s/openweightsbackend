from fastapi import Request

from app.main import api_rate_limiter
from app.middleware.rate_limit import client_ip


def test_api_rate_limit_allows_configured_requests_and_sets_headers(client):
    original_max = api_rate_limiter.max_requests
    try:
        api_rate_limiter.max_requests = 2
        first = client.get("/api/v1/health")
        second = client.get("/api/v1/health")

        assert first.status_code == 200
        assert first.headers["X-RateLimit-Limit"] == "2"
        assert first.headers["X-RateLimit-Remaining"] == "1"
        assert second.status_code == 200
        assert second.headers["X-RateLimit-Remaining"] == "0"
    finally:
        api_rate_limiter.max_requests = original_max


def test_api_rate_limit_returns_429_and_retry_after(client):
    original_max = api_rate_limiter.max_requests
    try:
        api_rate_limiter.max_requests = 1
        assert client.get("/api/v1/health").status_code == 200

        response = client.get("/api/v1/health")

        assert response.status_code == 429
        assert response.json() == {"detail": "Too many requests. Please try again later."}
        assert response.headers["Retry-After"].isdigit()
        assert response.headers["X-RateLimit-Limit"] == "1"
        assert response.headers["X-RateLimit-Remaining"] == "0"
    finally:
        api_rate_limiter.max_requests = original_max


def test_api_rate_limiter_expiry_allows_request_again():
    from app.middleware.rate_limit import InMemoryRateLimiter

    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=10)
    assert limiter.check("198.51.100.10", now=100.0) == (True, 0, 0)
    assert limiter.check("198.51.100.10", now=105.0) == (False, 0, 5)
    assert limiter.check("198.51.100.10", now=110.0) == (True, 0, 0)


def test_forwarded_header_is_ignored_unless_direct_peer_is_trusted():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/health",
            "headers": [(b"x-forwarded-for", b"203.0.113.8")],
            "client": ("192.0.2.1", 1234),
        }
    )

    assert (
        client_ip(request, trusted_proxy_ips=set(), proxy_header="X-Forwarded-For")
        == "192.0.2.1"
    )
    assert (
        client_ip(request, trusted_proxy_ips={"192.0.2.1"}, proxy_header="X-Forwarded-For")
        == "203.0.113.8"
    )


def test_non_api_request_is_not_rate_limited(client):
    original_max = api_rate_limiter.max_requests
    try:
        api_rate_limiter.max_requests = 1
        assert client.get("/").status_code == 200
        assert client.get("/").status_code == 200
    finally:
        api_rate_limiter.max_requests = original_max
