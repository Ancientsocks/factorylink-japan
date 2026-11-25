#!/usr/bin/env python3
"""Verify Redis-backed request-limit expiry and client isolation."""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import time

from redis import Redis
from starlette.requests import Request

from app import rate_limiting
from app.rate_limiting import RateLimitRule
from app.config import settings


def _request(client_ip: str) -> Request:
    path = "/api/v1/rate-limit-acceptance"
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"x-forwarded-for", client_ip.encode())],
        "client": ("192.0.2.1", 1234),
        "server": ("testserver", 80),
    })


def main() -> None:
    addresses = (
        str(ipaddress.ip_address(f"198.18.{int(time.time()) % 200}.{int(time.time_ns()) % 254 + 1}")),
        str(ipaddress.ip_address(f"198.18.{int(time.time()) % 200}.{(int(time.time_ns()) + 1) % 254 + 1}")),
    )
    rule_name = "redis-acceptance"
    keys = [
        "factorylink:rate:" + hashlib.sha256(f"{rule_name}:{address}".encode()).hexdigest()
        for address in addresses
    ]
    redis_client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    original_rules = rate_limiting.api_rules
    try:
        redis_client.ping()
        redis_client.delete(*keys)
        rate_limiting.api_rules = lambda _path, _method: (RateLimitRule(rule_name, 1, 2),)
        if asyncio.run(rate_limiting.enforce_api_rate_limit(_request(addresses[0]))) != 0:
            raise RuntimeError("The first request was unexpectedly rate limited.")
        retry_after = asyncio.run(rate_limiting.enforce_api_rate_limit(_request(addresses[0])))
        if not 1 <= retry_after <= 2:
            raise RuntimeError(f"Redis did not enforce the configured window: retry_after={retry_after}.")
        if asyncio.run(rate_limiting.enforce_api_rate_limit(_request(addresses[1]))) != 0:
            raise RuntimeError("Rate-limit counters were not isolated by client identity.")
        time.sleep(2.1)
        if asyncio.run(rate_limiting.enforce_api_rate_limit(_request(addresses[0]))) != 0:
            raise RuntimeError("The Redis rate-limit key did not expire after its window.")
        print("Redis rate-limit acceptance passed: limit, client isolation and expiry.")
    finally:
        rate_limiting.api_rules = original_rules
        redis_client.delete(*keys)
        redis_client.close()


if __name__ == "__main__":
    main()
