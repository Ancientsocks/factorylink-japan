from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _wait_for_url(url: str, process: subprocess.Popen, timeout: float, logs: Path) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not reachable yet"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = logs.read_text(errors="replace") if logs.exists() else ""
            raise RuntimeError(f"Service exited with code {process.returncode}: {url}\n{output}")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # service is expected to need a short warm-up
            last_error = str(exc)
        time.sleep(0.5)
    output = logs.read_text(errors="replace") if logs.exists() else ""
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}\n{output}")


@pytest.fixture(scope="session")
def app_server():
    external_base_url = os.getenv("FACTORYLINK_E2E_BASE_URL", "").rstrip("/")
    if external_base_url:
        parsed_url = urllib.parse.urlsplit(external_base_url)
        if (
            parsed_url.scheme != "http"
            or parsed_url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed_url.username
            or parsed_url.password
            or parsed_url.path not in {"", "/"}
        ):
            pytest.exit(
                "FACTORYLINK_E2E_BASE_URL must be an HTTP loopback staging URL.",
                returncode=2,
            )
        try:
            with urllib.request.urlopen(
                f"{external_base_url}/health/ready", timeout=5
            ) as response:
                if response.status != 200:
                    pytest.exit(
                        f"External staging readiness returned HTTP {response.status}.",
                        returncode=2,
                    )
        except Exception as exc:
            pytest.exit(
                f"External staging is not ready at {external_base_url}: {exc}",
                returncode=2,
            )
        yield {"base_url": external_base_url, "database": None}
        return

    vite = FRONTEND / "node_modules" / ".bin" / ("vite.cmd" if os.name == "nt" else "vite")
    if not vite.exists():
        pytest.exit(
            "Frontend dependencies are missing. Run `npm install` in frontend/ before browser tests.",
            returncode=2,
        )
    node = shutil.which("node")
    vite_script = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if not node or not vite_script.is_file():
        pytest.exit("Node.js and the local Vite executable are required for browser tests.", returncode=2)

    temp_dir = Path(tempfile.mkdtemp(prefix="factorylink-e2e-"))
    db_path = temp_dir / "factorylink-e2e.sqlite3"
    backend_log = temp_dir / "backend.log"
    frontend_log = temp_dir / "frontend.log"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        backend_port = sock.getsockname()[1]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        frontend_port = sock.getsockname()[1]
    while frontend_port == backend_port:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            frontend_port = sock.getsockname()[1]
    backend_url = f"http://127.0.0.1:{backend_port}"
    frontend_url = f"http://127.0.0.1:{frontend_port}"

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "AUTO_CREATE_SCHEMA": "true",
            "SEED_DEMO_DATA": "true",
            "ALLOW_PUBLIC_REGISTRATION": "true",
            "ENVIRONMENT": "development",
            "JWT_SECRET_KEY": "factorylink-e2e-only-secret-key-change-this-2026",
            "CORS_ORIGINS": frontend_url,
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            "FRONTEND_BASE_URL": frontend_url,
            "EXPOSE_AUTH_ACTION_LINKS": "true",
            "UPLOAD_DIR": str(temp_dir / "uploads"),
            "PYTHONUNBUFFERED": "1",
        }
    )
    Path(env["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)

    backend = None
    frontend = None
    try:
        with backend_log.open("w") as backend_stream:
            backend = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(backend_port)],
                cwd=BACKEND,
                env=env,
                stdout=backend_stream,
                stderr=subprocess.STDOUT,
            )
        vite_env = env.copy()
        vite_env["VITE_PROXY_TARGET"] = backend_url
        with frontend_log.open("w") as frontend_stream:
            frontend = subprocess.Popen(
                [node, str(vite_script), "--host", "127.0.0.1", "--port", str(frontend_port), "--strictPort"],
                cwd=FRONTEND,
                env=vite_env,
                stdout=frontend_stream,
                stderr=subprocess.STDOUT,
            )

        _wait_for_url(f"{backend_url}/health", backend, 90, backend_log)
        _wait_for_url(f"{frontend_url}/", frontend, 90, frontend_log)
        yield {"base_url": frontend_url, "database": db_path}
    finally:
        for process in (frontend, backend):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        # Keep logs only when explicitly requested to aid local debugging.
        if os.getenv("FACTORYLINK_KEEP_E2E_LOGS"):
            print(f"FactoryLink E2E logs retained at {temp_dir}")
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def playwright_instance() -> Playwright:
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Browser:
    options = {"headless": True}
    executable = os.getenv("CHROMIUM_EXECUTABLE_PATH")
    if not executable and not Path(playwright_instance.chromium.executable_path).exists():
        # Fall back to a system browser only when Playwright's pinned browser
        # has not been installed. CI and normal local runs prefer the managed build.
        for candidate in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
            executable = shutil.which(candidate)
            if executable:
                break
    if executable:
        options["executable_path"] = executable
    browser = playwright_instance.chromium.launch(**options)
    yield browser
    browser.close()


@pytest.fixture
def browser_context(browser: Browser) -> BrowserContext:
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    yield context
    context.close()


@pytest.fixture
def page(app_server: dict, browser_context: BrowserContext) -> Page:
    page = browser_context.new_page()
    page.set_default_timeout(12_000)
    page.goto(app_server["base_url"])
    return page
