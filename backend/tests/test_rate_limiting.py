import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from starlette.requests import Request

from app import main as main_module
from app import rate_limiting
from app.main import app


class FakeRedis:
    def __init__(self, clock):
        self.clock = clock
        self.counters = {}
        self.closed = False

    async def eval(self, _script, key_count, *arguments):
        keys = arguments[:key_count]
        limits_and_windows = arguments[key_count:]
        blocked_for = 0
        for index, key in enumerate(keys):
            limit, window = limits_and_windows[index * 2:index * 2 + 2]
            count, expires_at = self.counters.get(key, (0, 0))
            if expires_at <= self.clock[0]:
                count, expires_at = 0, self.clock[0] + window
            count += 1
            self.counters[key] = (count, expires_at)
            if count > limit:
                blocked_for = max(blocked_for, int(expires_at - self.clock[0]) or 1)
        return blocked_for

    async def aclose(self):
        self.closed = True


def make_request(path="/api/v1/auth/login", method="POST", forwarded="198.51.100.10"):
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("192.0.2.4", 1234),
        "server": ("testserver", 80),
    })


def test_sensitive_endpoints_have_separate_configurable_buckets(monkeypatch):
    monkeypatch.setattr(rate_limiting.settings, "api_rate_limit_per_minute", 120)
    monkeypatch.setattr(rate_limiting.settings, "auth_rate_limit_per_minute", 7)
    monkeypatch.setattr(rate_limiting.settings, "password_reset_rate_limit_per_minute", 2)

    assert rate_limiting.api_rules("/api/v1/auth/login", "POST") == (
        rate_limiting.RateLimitRule("api", 120),
        rate_limiting.RateLimitRule("login", 7),
    )
    assert rate_limiting.api_rules("/api/v1/auth/password-reset/request", "POST")[-1] == rate_limiting.RateLimitRule("password-reset", 2)
    assert rate_limiting.api_rules("/api/v1/auth/refresh", "GET") == (rate_limiting.RateLimitRule("api", 120),)
    assert rate_limiting.api_rules("/api/v1/auth/refresh", "POST")[-1].name == "refresh"


def test_redis_rate_limit_enforces_window_and_client_isolation(monkeypatch):
    monkeypatch.setattr(rate_limiting.settings, "api_rate_limit_per_minute", 10)
    monkeypatch.setattr(rate_limiting.settings, "auth_rate_limit_per_minute", 2)
    clock = [100.0]
    client = FakeRedis(clock)
    monkeypatch.setattr(rate_limiting.Redis, "from_url", lambda *args, **kwargs: client)

    async def check(path, ip):
        return await rate_limiting.enforce_api_rate_limit(make_request(path, forwarded=ip))

    assert asyncio.run(check("/api/v1/auth/login", "198.51.100.10")) == 0
    assert asyncio.run(check("/api/v1/auth/login", "198.51.100.10")) == 0
    assert asyncio.run(check("/api/v1/auth/login", "198.51.100.10")) == 60
    assert asyncio.run(check("/api/v1/auth/login", "198.51.100.11")) == 0
    clock[0] += 61
    assert asyncio.run(check("/api/v1/auth/login", "198.51.100.10")) == 0
    assert client.closed


def test_invalid_forwarded_address_uses_peer_address():
    request = make_request(forwarded="not-an-ip")
    assert rate_limiting.client_identity(request) == "192.0.2.4"


def test_rate_limited_api_request_returns_retry_after(monkeypatch):
    monkeypatch.setattr(main_module.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(main_module, "enforce_api_rate_limit", lambda request: _async_value(24))
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={"email": "not-used@example.jp", "password": "not-used"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "24"
    assert "x-request-id" in response.headers


def test_rate_limit_fails_closed_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(main_module.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(main_module.settings, "rate_limit_fail_closed", True)

    async def unavailable(_request):
        raise RedisError("connection refused")

    monkeypatch.setattr(main_module, "enforce_api_rate_limit", unavailable)
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={"email": "not-used@example.jp", "password": "not-used"})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert "x-request-id" in response.headers


def test_health_endpoint_is_not_blocked_by_api_rate_limiter(monkeypatch):
    monkeypatch.setattr(main_module.settings, "rate_limit_enabled", True)

    async def unavailable(_request):
        raise AssertionError("health check must not consume API rate limits")

    monkeypatch.setattr(main_module, "enforce_api_rate_limit", unavailable)
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200


async def _async_value(value):
    return value
