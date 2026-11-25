#!/usr/bin/env python3
"""Run FactoryLink's reproducible local acceptance checks.

This runner deliberately separates checks that can execute on a normal Python
host from infrastructure checks that need Docker, PostgreSQL, Redis, npm or k6.
Missing infrastructure is reported as SKIP, never as a passing test.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DEMO_PASSWORD = "FactoryLink2026!"


@dataclass
class Result:
    name: str
    status: str
    detail: str = ""


RESULTS: list[Result] = []


def record(name: str, status: str, detail: str = "") -> None:
    RESULTS.append(Result(name, status, detail))
    marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(status, "[INFO]")
    print(f"{marker} {name}" + (f": {detail}" if detail else ""), flush=True)


def run_command(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 180,
) -> bool:
    print(f"\n$ {' '.join(command)}", flush=True)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        tail = (exc.stdout or "")[-3000:] if isinstance(exc.stdout, str) else ""
        record(name, "FAIL", f"timed out after {timeout}s\n{tail}")
        return False
    output = completed.stdout.strip().replace(DEMO_PASSWORD, "[redacted demo password]")
    if completed.returncode == 0:
        record(name, "PASS", output[-1200:] if output else "completed")
        return True
    record(name, "FAIL", f"exit={completed.returncode}\n{output[-5000:]}")
    return False


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
              token: str | None = None, expected: int = 200) -> tuple[int, Any, dict[str, str]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
            body = response.read()
            response_headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read()
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
    try:
        parsed: Any = json.loads(body.decode("utf-8")) if body else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = body.decode("utf-8", errors="replace")
    if status != expected:
        raise AssertionError(f"{method} {url} returned {status}, expected {expected}: {parsed}")
    return status, parsed, response_headers


def run_live_api_smoke(env: dict[str, str], log_path: Path) -> bool:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log_stream = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND,
        env=env,
        stdout=log_stream,
        stderr=subprocess.STDOUT,
    )
    log_stream.close()
    try:
        deadline = time.monotonic() + 30
        last_error = "not ready"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"API process exited with {process.returncode}")
            try:
                _, live, headers = http_json(f"{base}/health/live")
                if live.get("status") == "ok" and headers.get("x-request-id"):
                    break
            except Exception as exc:  # startup warm-up only
                last_error = str(exc)
            time.sleep(0.25)
        else:
            raise RuntimeError(f"API did not become live: {last_error}")

        _, metrics, _ = http_json(f"{base}/metrics")
        if "factorylink_http_requests_total" not in metrics:
            raise AssertionError("Prometheus metrics endpoint did not expose request counters")

        _, admin_login, _ = http_json(
            f"{base}/api/v1/auth/login",
            method="POST",
            payload={"email": "admin@factorylink.jp", "password": DEMO_PASSWORD},
        )
        admin_token = admin_login.get("access_token")
        if not admin_token:
            raise AssertionError("Factory administrator login returned no access token")
        _, dashboard, _ = http_json(f"{base}/api/v1/dashboard", token=admin_token)
        if not isinstance(dashboard, dict):
            raise AssertionError("Factory dashboard response was not an object")
        _, inventory_report, _ = http_json(f"{base}/api/v1/reports/inventory.csv", token=admin_token)
        if not isinstance(inventory_report, str) or "LOT-8831" not in inventory_report:
            raise AssertionError("Factory inventory CSV did not include seeded lot data")

        _, supplier_login, _ = http_json(
            f"{base}/api/v1/auth/login",
            method="POST",
            payload={"email": "supplier@osaka-parts.jp", "password": DEMO_PASSWORD},
        )
        supplier_token = supplier_login.get("access_token")
        if not supplier_token:
            raise AssertionError("Supplier login returned no access token")
        _, purchase_orders, _ = http_json(f"{base}/api/v1/purchase-orders", token=supplier_token)
        if not isinstance(purchase_orders, list) or len(purchase_orders) < 1:
            raise AssertionError("Supplier account did not receive its linked purchase orders")
        http_json(f"{base}/api/v1/inventory/batches", token=supplier_token, expected=403)
        http_json(f"{base}/api/v1/reports/inventory.csv", token=supplier_token, expected=403)

        # Exercise a complete supplier-to-factory workflow through a live ASGI
        # server, not only TestClient. Use a dedicated material so FIFO seed lots
        # cannot affect the quantities asserted below.
        _, suppliers, _ = http_json(f"{base}/api/v1/suppliers", token=admin_token)
        linked_supplier = next((row for row in suppliers if row.get("supplier_organization_id")), None)
        if not linked_supplier:
            raise AssertionError("Seeded linked supplier record was not available")
        po_number = "PO-ACCEPTANCE-LIVE-001"
        _, created_po, _ = http_json(
            f"{base}/api/v1/purchase-orders",
            method="POST",
            token=admin_token,
            payload={
                "supplier_id": linked_supplier["id"],
                "po_number": po_number,
                "item_name": "Acceptance Alloy",
                "quantity": 12,
                "unit": "kg",
                "unit_price": 125,
            },
            expected=201,
        )
        po_id = created_po["id"]
        http_json(
            f"{base}/api/v1/purchase-orders/{po_id}/status",
            method="PATCH", token=admin_token,
            payload={"status": "SUBMITTED", "note": "Live acceptance order"},
        )

        _, supplier_orders, _ = http_json(f"{base}/api/v1/purchase-orders", token=supplier_token)
        visible_po = next((row for row in supplier_orders if row.get("po_number") == po_number), None)
        if not visible_po:
            raise AssertionError("Supplier cannot see the purchase order shared with its organisation")
        http_json(
            f"{base}/api/v1/purchase-orders/{po_id}/status",
            method="PATCH", token=supplier_token,
            payload={"status": "CONFIRMED", "note": "Confirmed by acceptance supplier"},
        )
        http_json(
            f"{base}/api/v1/purchase-orders/{po_id}/status",
            method="PATCH", token=supplier_token,
            payload={"status": "IN_TRANSIT", "note": "Acceptance shipment dispatched"},
        )

        _, warehouse_login, _ = http_json(
            f"{base}/api/v1/auth/login", method="POST",
            payload={"email": "warehouse@factorylink.jp", "password": DEMO_PASSWORD},
        )
        warehouse_token = warehouse_login["access_token"]
        _, receipt, _ = http_json(
            f"{base}/api/v1/inventory/receipts",
            method="POST", token=warehouse_token,
            payload={
                "material_name": "Acceptance Alloy",
                "lot_number": "LOT-ACCEPTANCE-LIVE-001",
                "quantity": 12,
                "unit": "kg",
                "unit_cost": 125,
                "purchase_order_id": po_id,
                "reference": "GR-ACCEPTANCE-LIVE-001",
            },
            expected=201,
        )
        if receipt.get("purchase_order_id") != po_id:
            raise AssertionError("Goods receipt was not linked to its source purchase order")
        _, supplier_orders_after_receipt, _ = http_json(f"{base}/api/v1/purchase-orders", token=supplier_token)
        received_po = next((row for row in supplier_orders_after_receipt if row.get("po_number") == po_number), None)
        if not received_po or float(received_po.get("received_quantity", 0)) != 12 or received_po.get("status") != "DELIVERED":
            raise AssertionError(f"Supplier-visible receipt progress is incorrect: {received_po}")

        _, production_order, _ = http_json(
            f"{base}/api/v1/production/orders",
            method="POST", token=admin_token,
            payload={
                "order_number": "MO-ACCEPTANCE-LIVE-001",
                "product_name": "Acceptance Assembly",
                "quantity": 4,
                "material_name": "Acceptance Alloy",
                "material_required": 4,
            },
            expected=201,
        )
        production_id = production_order["id"]
        for status in ("READY", "IN_PROGRESS"):
            http_json(
                f"{base}/api/v1/production/orders/{production_id}/status",
                method="PATCH", token=admin_token, payload={"status": status},
            )
        http_json(
            f"{base}/api/v1/production/orders/{production_id}/progress",
            method="PATCH", token=admin_token,
            payload={"completed_quantity": 3, "rejected_quantity": 1},
        )
        http_json(
            f"{base}/api/v1/production/orders/{production_id}/status",
            method="PATCH", token=admin_token, payload={"status": "COMPLETED"},
        )

        _, quality_login, _ = http_json(
            f"{base}/api/v1/auth/login", method="POST",
            payload={"email": "quality@factorylink.jp", "password": DEMO_PASSWORD},
        )
        quality_token = quality_login["access_token"]
        _, inspection, _ = http_json(
            f"{base}/api/v1/quality/inspections",
            method="POST", token=quality_token,
            payload={
                "inspection_number": "QI-ACCEPTANCE-LIVE-001",
                "product_name": "Acceptance Assembly",
                "batch_id": receipt["id"],
                "result": "FAIL",
                "defect_count": 1,
                "sample_size": 4,
                "notes": "Acceptance workflow found a sample non-conformance.",
                "corrective_action": "Quarantine the lot and investigate the machining setup.",
            },
            expected=201,
        )
        _, trace, _ = http_json(
            f"{base}/api/v1/traceability/LOT-ACCEPTANCE-LIVE-001", token=admin_token,
        )
        event_types = {event.get("event_type") for event in trace.get("events", [])}
        required_events = {"GOODS_RECEIVED", "PRODUCTION_RESERVED", "PRODUCTION_CONSUMED", "QUALITY_HOLD"}
        if trace.get("batch", {}).get("status") != "HOLD" or not required_events.issubset(event_types):
            raise AssertionError(f"Traceability history incomplete: {event_types}")

        record(
            "Live API factory/supplier and full manufacturing workflow",
            "PASS",
            f"health, metrics, factory dashboard, supplier PO visibility/denials, linked receipt ({received_po['received_quantity']}/12 kg), production completion, failed quality inspection and traceability ({len(event_types)} event types)",
        )
        return True
    except Exception as exc:
        try:
            log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-5000:]
        except OSError:
            log_tail = ""
        record("Live API factory/supplier smoke", "FAIL", f"{exc}\n{log_tail}")
        return False
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_docker_compose_smoke(docker: str) -> bool:
    """Build and exercise an isolated Compose project, then remove only its resources."""
    port = free_port()
    project = f"factorylink-acceptance-{os.getpid()}-{time.time_ns()}"
    env = os.environ.copy()
    env.update({
        "APP_PORT": str(port),
        "ENVIRONMENT": "development",
        "POSTGRES_DB": "factorylink_acceptance",
        "POSTGRES_USER": "factorylink",
        "POSTGRES_PASSWORD": "factorylink_acceptance_db_password",
        "RUNTIME_DB_USER": "factorylink_app",
        "RUNTIME_DB_PASSWORD": "factorylink_acceptance_runtime_password",
        "JWT_SECRET_KEY": "factorylink-acceptance-compose-secret-never-deploy",
        "JWT_ALGORITHM": "HS256",
        "CORS_ORIGINS": f"http://localhost:{port}",
        "SEED_DEMO_DATA": "true",
        "ALLOW_PUBLIC_REGISTRATION": "true",
        "EXPOSE_AUTH_ACTION_LINKS": "true",
        "SMTP_HOST": "",
        "SMTP_USERNAME": "",
        "SMTP_PASSWORD": "",
        "SMTP_STARTTLS": "true",
        "FRONTEND_BASE_URL": f"http://localhost:{port}",
        "PYTHONUNBUFFERED": "1",
    })
    compose = [docker, "compose", "--project-name", project, "--env-file", ".env.example"]
    started = False
    try:
        print(f"\n$ {' '.join(compose + ['up', '--build', '--detach'])}", flush=True)
        try:
            up = subprocess.run(
                compose + ["up", "--build", "--detach"],
                cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=900, check=False,
            )
        except subprocess.TimeoutExpired:
            record("Docker Compose isolated runtime", "FAIL", "compose up/build timed out after 900 seconds")
            return False
        output = up.stdout.strip()
        output = output.replace(DEMO_PASSWORD, "[redacted demo password]")
        if up.returncode != 0:
            logs = subprocess.run(
                compose + ["logs", "--no-color", "--tail=100"], cwd=ROOT, env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=45, check=False,
            ).stdout
            record("Docker Compose isolated runtime", "FAIL", f"compose up exited {up.returncode}\n{output[-3500:]}\n{logs[-5000:]}")
            return False
        started = True

        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 180
        last_error = "not ready"
        while time.monotonic() < deadline:
            try:
                _, ready, _ = http_json(f"{base}/health/ready")
                if isinstance(ready, dict) and ready.get("status") == "ok":
                    break
            except Exception as exc:
                last_error = str(exc)
            time.sleep(2)
        else:
            raise RuntimeError(f"Compose application did not become ready: {last_error}")

        with urllib.request.urlopen(base + "/", timeout=10) as response:
            html = response.read().decode("utf-8", errors="replace")
            if response.status != 200 or "FactoryLink" not in html:
                raise AssertionError("Nginx frontend did not serve the FactoryLink SPA")
        with urllib.request.urlopen(base + "/docs", timeout=10) as response:
            if response.status != 200:
                raise AssertionError("FastAPI Swagger docs are not reachable through Nginx")

        _, admin_login, _ = http_json(
            f"{base}/api/v1/auth/login", method="POST",
            payload={"email": "admin@factorylink.jp", "password": DEMO_PASSWORD},
        )
        admin_token = admin_login.get("access_token")
        if not admin_token:
            raise AssertionError("Factory administrator login through Nginx returned no access token")
        _, dashboard, _ = http_json(f"{base}/api/v1/dashboard", token=admin_token)
        if not isinstance(dashboard, dict):
            raise AssertionError("Factory dashboard via the public frontend proxy did not return JSON")
        _, supplier_login, _ = http_json(
            f"{base}/api/v1/auth/login", method="POST",
            payload={"email": "supplier@osaka-parts.jp", "password": DEMO_PASSWORD},
        )
        supplier_token = supplier_login.get("access_token")
        if not supplier_token:
            raise AssertionError("Supplier login through Nginx returned no access token")
        _, supplier_orders, _ = http_json(f"{base}/api/v1/purchase-orders", token=supplier_token)
        if not supplier_orders or not isinstance(supplier_orders, list):
            raise AssertionError("Supplier portal through Nginx did not return linked purchase orders")
        http_json(f"{base}/api/v1/inventory/batches", token=supplier_token, expected=403)
        record(
            "Docker Compose isolated runtime",
            "PASS",
            f"9 services built/started; readiness, Nginx SPA, Swagger, factory dashboard, supplier portal ({len(supplier_orders)} orders) and supplier inventory denial verified",
        )
        return True
    except Exception as exc:
        extra = ""
        if started:
            logs = subprocess.run(
                compose + ["logs", "--no-color", "--tail=100"], cwd=ROOT, env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=45, check=False,
            ).stdout
            extra = f"\n{logs[-5000:]}"
        record("Docker Compose isolated runtime", "FAIL", f"{exc}{extra}")
        return False
    finally:
        # The project name is unique; `--volumes` can therefore only remove this
        # acceptance run's temporary DB/Redis/upload resources, never a user's app.
        try:
            down = subprocess.run(
                compose + ["down", "--volumes", "--remove-orphans"], cwd=ROOT, env=env,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=180, check=False,
            )
            if down.returncode == 0:
                record("Docker Compose acceptance cleanup", "PASS", "isolated containers, network and volumes removed")
            else:
                record("Docker Compose acceptance cleanup", "FAIL", down.stdout[-2500:])
        except (OSError, subprocess.TimeoutExpired) as exc:
            record("Docker Compose acceptance cleanup", "FAIL", f"cleanup command could not complete: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-backend-tests", action="store_true", help="Skip pytest backend regression suite")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when optional infrastructure checks are skipped")
    parser.add_argument("--with-docker-config", action="store_true", help="Run docker compose config if Docker CLI is installed")
    parser.add_argument("--with-docker-runtime", action="store_true", help="Build/start an isolated Docker Compose stack, smoke it through Nginx, then remove its own resources")
    parser.add_argument("--with-frontend-build", action="store_true", help="Run npm build if frontend dependencies are installed")
    parser.add_argument("--with-browser-e2e", action="store_true", help="Run Playwright journeys if frontend dependencies and browser are installed")
    parser.add_argument("--with-postgres", action="store_true", help="Run scripts/db/postgres-acceptance.sh against supplied PG* environment")
    parser.add_argument("--report", type=Path, default=None, help="Write JSON result report to this path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("FactoryLink reproducible acceptance runner")
    print(f"Root: {ROOT}")

    base_env = os.environ.copy()
    if not args.skip_backend_tests:
        run_command("Backend regression suite", [sys.executable, "-m", "pytest", "-q"], cwd=BACKEND, env=base_env, timeout=240)
    else:
        record("Backend regression suite", "SKIP", "disabled by command line")

    run_command("Python compile check", [sys.executable, "-m", "compileall", "-q", "app", "migrations", "tests"], cwd=BACKEND, env=base_env)

    with tempfile.TemporaryDirectory(prefix="factorylink-acceptance-") as temp_name:
        temp = Path(temp_name)
        db_file = temp / "factorylink-acceptance.sqlite3"
        upload_dir = temp / "uploads"
        upload_dir.mkdir()
        env = base_env.copy()
        env.update({
            "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
            "AUTO_CREATE_SCHEMA": "false",
            "SEED_DEMO_DATA": "true",
            "ALLOW_PUBLIC_REGISTRATION": "true",
            "ENVIRONMENT": "development",
            "JWT_SECRET_KEY": "factorylink-acceptance-only-secret-2026-do-not-deploy",
            "JWT_ALGORITHM": "HS256",
            "CORS_ORIGINS": "http://127.0.0.1:5173",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            "FRONTEND_BASE_URL": "http://127.0.0.1:5173",
            "EXPOSE_AUTH_ACTION_LINKS": "true",
            "SMTP_HOST": "",
            "SMTP_USERNAME": "",
            "SMTP_PASSWORD": "",
            "SMTP_STARTTLS": "true",
            "UPLOAD_DIR": str(upload_dir),
            "PYTHONUNBUFFERED": "1",
        })
        migrate_ok = run_command(
            "Fresh Alembic migration",
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env=env,
            timeout=120,
        )
        seed_one = run_command("Demo seed first run", [sys.executable, "-m", "app.seed"], cwd=BACKEND, env=env, timeout=120)
        seed_two = run_command("Demo seed idempotency", [sys.executable, "-m", "app.seed"], cwd=BACKEND, env=env, timeout=120)
        if migrate_ok and seed_one and seed_two:
            run_live_api_smoke(env, temp / "api.log")
        else:
            record("Live API factory/supplier smoke", "SKIP", "migration or demo seed failed")

    # Optional gates are deliberately reported as SKIP when prerequisites are absent.
    docker = shutil.which("docker")
    if args.with_docker_config:
        if docker:
            run_command("Docker Compose configuration", [docker, "compose", "--env-file", ".env.example", "config", "--quiet"], cwd=ROOT, env=base_env)
        else:
            record("Docker Compose configuration", "SKIP", "Docker CLI not installed")
    else:
        record("Docker Compose configuration", "SKIP", "opt in with --with-docker-config")

    if args.with_docker_runtime:
        if docker:
            run_docker_compose_smoke(docker)
        else:
            record("Docker Compose isolated runtime", "SKIP", "Docker CLI/daemon not installed")
    else:
        record("Docker Compose isolated runtime", "SKIP", "opt in with --with-docker-runtime; uses an isolated project name and temporary volumes")

    if args.with_frontend_build:
        npm = shutil.which("npm")
        if npm and (FRONTEND / "node_modules").is_dir():
            run_command("Vite production build", [npm, "run", "build"], cwd=FRONTEND, env=base_env, timeout=240)
        else:
            record("Vite production build", "SKIP", "npm or frontend/node_modules is missing")
    else:
        record("Vite production build", "SKIP", "opt in with --with-frontend-build after npm install")

    if args.with_browser_e2e:
        if (FRONTEND / "node_modules").is_dir() and shutil.which("pytest"):
            run_command("Playwright browser journeys", [sys.executable, "-m", "pytest", "-q", "e2e"], cwd=ROOT, env=base_env, timeout=300)
        else:
            record("Playwright browser journeys", "SKIP", "frontend dependencies or pytest are missing")
    else:
        record("Playwright browser journeys", "SKIP", "opt in with --with-browser-e2e after frontend install and Playwright browser setup")

    if args.with_postgres:
        if shutil.which("psql") and base_env.get("PGPASSWORD") and base_env.get("RUNTIME_DB_PASSWORD"):
            run_command("PostgreSQL/Redis/Celery acceptance", ["bash", "scripts/db/postgres-acceptance.sh"], cwd=ROOT, env=base_env, timeout=420)
        else:
            record("PostgreSQL/Redis/Celery acceptance", "SKIP", "psql or required PG*/RUNTIME_DB_PASSWORD environment is missing")
    else:
        record("PostgreSQL/Redis/Celery acceptance", "SKIP", "requires PostgreSQL 17, Redis, drivers and explicit --with-postgres")

    passed = sum(result.status == "PASS" for result in RESULTS)
    failed = sum(result.status == "FAIL" for result in RESULTS)
    skipped = sum(result.status == "SKIP" for result in RESULTS)
    summary = {"passed": passed, "failed": failed, "skipped": skipped}
    print("\nSummary: " + json.dumps(summary))
    if args.report:
        report_path = args.report if args.report.is_absolute() else ROOT / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project_version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            "summary": summary,
            "results": [asdict(item) for item in RESULTS],
        }, indent=2), encoding="utf-8")
        print(f"Report written to: {report_path}")

    if failed:
        return 1
    if args.strict and skipped:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
