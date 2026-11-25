"""Enqueue a tenant-aware maintenance reminder task and wait for completion."""
from __future__ import annotations

import time
from app.celery_app import celery_app


def main() -> None:
    inspector = celery_app.control.inspect(timeout=2)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            replies = inspector.ping() or {}
            if replies:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise SystemExit("Celery worker did not respond to ping")

    result = celery_app.send_task("app.tasks.create_maintenance_reminders")
    value = result.get(timeout=45, propagate=True)
    if not isinstance(value, dict) or "notifications_created" not in value:
        raise SystemExit(f"Unexpected maintenance task result: {value!r}")
    print(f"Celery/Redis/PostgreSQL task passed: {value}")


if __name__ == "__main__":
    main()
