#!/usr/bin/env python3
"""Conservative authenticated read-load check for an isolated staging deployment."""
from __future__ import annotations

import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from collections import Counter


def main() -> int:
    base_url = os.environ.get("LOADTEST_BASE_URL", "").rstrip("/")
    token = os.environ.get("LOADTEST_BEARER_TOKEN", "")
    if not base_url.startswith("https://") or not token:
        print("Set HTTPS LOADTEST_BASE_URL and a dedicated staging LOADTEST_BEARER_TOKEN.", file=sys.stderr)
        return 2
    try:
        users = int(os.environ.get("LOADTEST_USERS", "10"))
        duration = int(os.environ.get("LOADTEST_DURATION_SECONDS", "60"))
        interval = float(os.environ.get("LOADTEST_INTERVAL_SECONDS", "30"))
        p95_limit_ms = float(os.environ.get("LOADTEST_P95_LIMIT_MS", "1000"))
    except ValueError:
        print("Load-test numeric settings must be valid numbers.", file=sys.stderr)
        return 2
    if not 1 <= users <= 50 or not 1 <= duration <= 300 or not 1 <= interval <= 300 or p95_limit_ms <= 0:
        print("Use 1-50 users, 1-300 seconds, a 1-300 second interval, and a positive p95 limit.", file=sys.stderr)
        return 2

    url = f"{base_url}/api/v1/dashboard"
    stop_at = time.monotonic() + duration
    samples: list[float] = []
    statuses: Counter[int] = Counter()
    transport_errors: Counter[str] = Counter()
    lock = threading.Lock()

    def virtual_user() -> None:
        while time.monotonic() < stop_at:
            request = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                method="GET",
            )
            started = time.perf_counter()
            status = 0
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    status = response.status
                    response.read()
            except urllib.error.HTTPError as error:
                status = error.code
                error.read()
            except Exception as error:
                status = 0
                with lock:
                    transport_errors[type(error).__name__] += 1
            elapsed_ms = (time.perf_counter() - started) * 1000
            with lock:
                samples.append(elapsed_ms)
                statuses[status] += 1
            time.sleep(min(interval, max(0, stop_at - time.monotonic())))

    with ThreadPoolExecutor(max_workers=users) as pool:
        futures = [pool.submit(virtual_user) for _ in range(users)]
        for future in futures:
            future.result()

    if not samples:
        print("No load samples were recorded.", file=sys.stderr)
        return 1
    ordered = sorted(samples)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))]
    error_requests = sum(count for status, count in statuses.items() if not 200 <= status < 300)
    print(
        f"users={users} duration_seconds={duration} interval_seconds={interval:g} "
        f"requests={len(samples)} statuses={dict(statuses)} "
        f"latency_ms_avg={statistics.mean(samples):.1f} "
        f"latency_ms_p95={p95:.1f} latency_ms_max={max(samples):.1f} "
        f"error_requests={error_requests} transport_errors={dict(transport_errors)} p95_limit_ms={p95_limit_ms:g}"
    )
    return 0 if error_requests == 0 and p95 <= p95_limit_ms else 1


if __name__ == "__main__":
    raise SystemExit(main())
