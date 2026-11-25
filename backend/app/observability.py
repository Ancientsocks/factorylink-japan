"""Small dependency-free request observability helpers for FactoryLink.

Metrics are process-local counters intended for internal scrape/diagnostics.
For multi-worker or multi-instance deployments, aggregate them in a monitoring
system or replace this adapter with a shared metrics backend.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Emit one compact JSON object per log line without serialising secrets."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        details = getattr(record, "factorylink", None)
        if isinstance(details, dict):
            payload.update(details)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_access_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("factorylink.access")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger


class RequestMetrics:
    """Thread-safe low-cardinality HTTP counters and duration totals."""

    def __init__(self) -> None:
        from collections import defaultdict
        from threading import Lock

        self._counts = defaultdict(int)
        self._duration_sums = defaultdict(float)
        self._lock = Lock()

    def observe(self, method: str, route: str, status_code: int, duration_seconds: float) -> None:
        key = (method, route, int(status_code))
        with self._lock:
            self._counts[key] += 1
            self._duration_sums[key] += max(0.0, float(duration_seconds))

    def render_prometheus(self) -> str:
        lines = [
            "# HELP factorylink_http_requests_total Total HTTP requests handled by this process.",
            "# TYPE factorylink_http_requests_total counter",
        ]
        with self._lock:
            items = sorted(self._counts.items())
            duration_items = sorted(self._duration_sums.items())
        for (method, route, status), count in items:
            labels = f'method="{method}",route="{route}",status="{status}"'
            lines.append(f"factorylink_http_requests_total{{{labels}}} {count}")
        lines.extend([
            "# HELP factorylink_http_request_duration_seconds_sum Total HTTP request duration in seconds.",
            "# TYPE factorylink_http_request_duration_seconds_sum counter",
        ])
        for (method, route, status), total in duration_items:
            labels = f'method="{method}",route="{route}",status="{status}"'
            lines.append(f"factorylink_http_request_duration_seconds_sum{{{labels}}} {total:.6f}")
        return "\n".join(lines) + "\n"
