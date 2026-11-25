"""Redis-backed fixed-window API request limiting."""
from __future__ import annotations

import hashlib
import ipaddress
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from redis.asyncio import Redis

from .config import settings


_INCREMENT_SCRIPT = """
local max_retry = 1
local blocked = false
for i, key in ipairs(KEYS) do
    local count = redis.call('INCR', key)
    if count == 1 then
        redis.call('EXPIRE', key, ARGV[(i - 1) * 2 + 2])
    end
    local ttl = redis.call('TTL', key)
    if count > tonumber(ARGV[(i - 1) * 2 + 1]) then
        blocked = true
        if ttl > max_retry then
            max_retry = ttl
        end
    end
end
if blocked then
    return max_retry
end
return 0
"""


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int = 60


def api_rules(path: str, method: str) -> tuple[RateLimitRule, ...]:
    rules = [
        RateLimitRule("api", settings.api_rate_limit_per_minute),
    ]
    sensitive = {
        ("POST", "/api/v1/auth/login"): ("login", settings.auth_rate_limit_per_minute),
        ("POST", "/api/v1/auth/refresh"): ("refresh", settings.auth_rate_limit_per_minute),
        ("POST", "/api/v1/organizations/register"): ("registration", settings.registration_rate_limit_per_minute),
        ("POST", "/api/v1/auth/password-reset/request"): ("password-reset", settings.password_reset_rate_limit_per_minute),
        ("POST", "/api/v1/auth/password-reset/confirm"): ("password-reset-confirm", settings.password_reset_rate_limit_per_minute),
        ("POST", "/api/v1/auth/email-verification/request"): ("email-code", settings.password_reset_rate_limit_per_minute),
        ("POST", "/api/v1/auth/email-verification/verify"): ("email-code-verify", settings.auth_rate_limit_per_minute),
        ("GET", "/api/v1/auth/google/start"): ("google-start", settings.auth_rate_limit_per_minute),
        ("POST", "/api/v1/auth/google/exchange"): ("google-exchange", settings.password_reset_rate_limit_per_minute),
        ("POST", "/api/v1/auth/google/register"): ("google-register", settings.registration_rate_limit_per_minute),
        ("POST", "/api/v1/users/invitations"): ("invitation-create", settings.auth_rate_limit_per_minute),
        ("POST", "/api/v1/users/invitations/accept"): ("invitation-accept", settings.password_reset_rate_limit_per_minute),
    }.get((method.upper(), path))
    if sensitive:
        rules.append(RateLimitRule(sensitive[0], sensitive[1]))
    return tuple(rules)


def client_identity(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    candidate = forwarded or (request.client.host if request.client else "unknown")
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        peer = request.client.host if request.client else "unknown"
        try:
            return str(ipaddress.ip_address(peer))
        except ValueError:
            return "unknown"


async def enforce_api_rate_limit(
    request: Request,
    *,
    redis_factory: Any | None = None,
) -> int:
    """Return seconds to wait, or zero when allowed; Redis failures are explicit."""
    factory = redis_factory or Redis.from_url
    client = factory(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=settings.rate_limit_redis_timeout_seconds,
        socket_timeout=settings.rate_limit_redis_timeout_seconds,
    )
    identity = client_identity(request)
    keys = [
        "factorylink:rate:" + hashlib.sha256(f"{rule.name}:{identity}".encode()).hexdigest()
        for rule in api_rules(request.url.path, request.method)
    ]
    arguments: list[int] = []
    for rule in api_rules(request.url.path, request.method):
        arguments.extend((rule.limit, rule.window_seconds))
    try:
        result = await client.eval(_INCREMENT_SCRIPT, len(keys), *keys, *arguments)
        return max(0, int(result))
    finally:
        await client.aclose()
