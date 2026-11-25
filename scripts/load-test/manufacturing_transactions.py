#!/usr/bin/env python3
"""Bounded concurrent manufacturing, inventory, and dashboard staging load test."""
from __future__ import annotations

import json
import os
import secrets
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


def _settings() -> tuple[str, str, int, int, int, int, float, float]:
    base_url = os.environ.get("LOADTEST_BASE_URL", "").rstrip("/")
    token = os.environ.get("LOADTEST_BEARER_TOKEN", "")
    parsed = urllib.parse.urlsplit(base_url)
    local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if not ((parsed.scheme == "https" or local_http) and parsed.netloc and not parsed.username and not parsed.password):
        raise ValueError("Set LOADTEST_BASE_URL to HTTPS staging, or HTTP on loopback only.")
    if not token:
        raise ValueError("Set LOADTEST_BEARER_TOKEN for a dedicated staging ORG_ADMIN user.")
    try:
        users = int(os.environ.get("LOADTEST_USERS", "10"))
        duration = int(os.environ.get("LOADTEST_DURATION_SECONDS", "60"))
        max_operations = int(os.environ.get("LOADTEST_MAX_OPERATIONS", "200"))
        requests_per_minute = int(os.environ.get("LOADTEST_REQUESTS_PER_MINUTE", "90"))
        p95_limit_ms = float(os.environ.get("LOADTEST_P95_LIMIT_MS", "1000"))
        timeout = float(os.environ.get("LOADTEST_REQUEST_TIMEOUT_SECONDS", "15"))
    except ValueError as exc:
        raise ValueError("Load-test numeric settings must be valid numbers.") from exc
    if not 1 <= users <= 50 or not 1 <= duration <= 300:
        raise ValueError("Use 1-50 concurrent users and a 1-300 second duration.")
    if not 1 <= max_operations <= 2000 or not 1 <= requests_per_minute <= 6000:
        raise ValueError("Use 1-2,000 operations and a 1-6,000 request-per-minute client pace.")
    if p95_limit_ms <= 0 or not 1 <= timeout <= 120:
        raise ValueError("Use 1-2,000 operations, a positive p95 limit, and 1-120 second timeouts.")
    return base_url, token, users, duration, max_operations, requests_per_minute, p95_limit_ms, timeout


def main() -> int:
    try:
        base_url, token, users, duration, max_operations, requests_per_minute, p95_limit_ms, timeout = _settings()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    stop_at = time.monotonic() + duration
    run_id = secrets.token_hex(5)
    lock = threading.Lock()
    latencies_ms: list[float] = []
    statuses: Counter[int] = Counter()
    transport_errors: Counter[str] = Counter()
    operation_counts: Counter[str] = Counter()
    scheduled = 0
    failed_operations = 0
    next_request_at = time.monotonic()
    request_interval = 60.0 / requests_per_minute

    def send(path: str, method: str, payload: dict | None = None) -> tuple[int, dict | None]:
        nonlocal next_request_at
        while True:
            with lock:
                delay = next_request_at - time.monotonic()
                if delay <= 0:
                    next_request_at = time.monotonic() + request_interval
                    break
            time.sleep(delay)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{base_url}{path}", data=body, headers=headers, method=method,
        )
        started = time.perf_counter()
        status = 0
        response_body = b""
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.status
                response_body = response.read()
        except urllib.error.HTTPError as error:
            status = error.code
            response_body = error.read()
        except Exception as error:
            with lock:
                transport_errors[type(error).__name__] += 1
        elapsed = (time.perf_counter() - started) * 1000
        with lock:
            statuses[status] += 1
            latencies_ms.append(elapsed)
        if not response_body:
            return status, None
        decoded = json.loads(response_body)
        return status, decoded if isinstance(decoded, dict) else None

    def manufacturing_workflow(worker_id: int, sequence: int) -> bool:
        unique = f"{run_id}-{worker_id}-{sequence}"
        status, order = send("/api/v1/production/orders", "POST", {
            "order_number": f"LT-MO-{unique}",
            "product_name": "Load Test Finished Part",
            "quantity": 1,
            "material_name": "",
            "material_required": 0,
            "track_serials": True,
        })
        if status != 201 or not order:
            return False
        order_id = order.get("id")
        for next_status in ("READY", "IN_PROGRESS"):
            status, _ = send(
                f"/api/v1/production/orders/{order_id}/status",
                "PATCH",
                {"status": next_status},
            )
            if status != 200:
                return False
        status, _ = send(
            f"/api/v1/production/orders/{order_id}/progress",
            "PATCH",
            {"completed_quantity": 1, "rejected_quantity": 0},
        )
        if status != 200:
            return False
        status, _ = send(
            f"/api/v1/production/orders/{order_id}/status",
            "PATCH",
            {"status": "COMPLETED"},
        )
        return status == 200

    def virtual_user(worker_id: int) -> None:
        nonlocal scheduled, failed_operations
        sequence = 0
        while time.monotonic() < stop_at:
            with lock:
                if scheduled >= max_operations:
                    return
                operation = scheduled
                scheduled += 1
            sequence += 1
            if operation % 5 in (0, 1, 2):
                name = "manufacturing"
                succeeded = manufacturing_workflow(worker_id, sequence)
            elif operation % 5 == 3:
                name = "inventory_receipt"
                unique = f"{run_id}-{worker_id}-{sequence}"
                status, _ = send("/api/v1/inventory/receipts", "POST", {
                    "material_name": "Load Test Component",
                    "lot_number": f"LT-{unique}",
                    "quantity": 1,
                    "unit": "pcs",
                    "unit_cost": 1,
                    "reference": f"LT-REF-{unique}",
                })
                succeeded = status == 201
            else:
                name = "dashboard_read"
                status, _ = send("/api/v1/dashboard", "GET")
                succeeded = 200 <= status < 300
            with lock:
                operation_counts[name] += 1
                if not succeeded:
                    failed_operations += 1

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=users) as pool:
        futures = [pool.submit(virtual_user, worker) for worker in range(users)]
        for future in futures:
            future.result()
    elapsed = max(time.perf_counter() - started, 1e-9)

    ordered = sorted(latencies_ms)
    if not ordered:
        print("No load samples were recorded.", file=sys.stderr)
        return 1

    def percentile(value: float) -> float:
        return ordered[min(len(ordered) - 1, int(value * (len(ordered) - 1)))]

    errors = sum(count for status, count in statuses.items() if not 200 <= status < 300)
    report = {
        "workload": "60% complete manufacturing lifecycle, 20% unique inventory receipts, 20% dashboard reads",
        "users": users,
        "duration_seconds": round(elapsed, 3),
        "workload_operations": scheduled,
        "request_pacing_per_minute": requests_per_minute,
        "operation_counts": dict(operation_counts),
        "failed_operations": failed_operations,
        "http_requests": len(ordered),
        "throughput_http_requests_per_second": round(len(ordered) / elapsed, 2),
        "statuses": dict(statuses),
        "error_requests": errors,
        "transport_errors": dict(transport_errors),
        "latency_ms_avg": round(statistics.mean(ordered), 2),
        "latency_ms_p50": round(percentile(0.50), 2),
        "latency_ms_p95": round(percentile(0.95), 2),
        "latency_ms_p99": round(percentile(0.99), 2),
        "latency_ms_max": round(max(ordered), 2),
        "p95_limit_ms": p95_limit_ms,
        "server_resource_usage": (
            "Not observable over HTTP; capture docker stats or provider CPU/memory, "
            "database connections/IO, and Redis metrics during the run."
        ),
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if errors == 0 and failed_operations == 0 and report["latency_ms_p95"] <= p95_limit_ms else 1


if __name__ == "__main__":
    raise SystemExit(main())
