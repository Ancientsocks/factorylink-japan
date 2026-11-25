# FactoryLink RC11 Build Report

**Date:** 2026-11-03  
**Release:** Japan Local RC11 — Browser Acceptance Foundation  
**Disposition:** Local evaluation release; not production certified.

## Delivered

- Five Playwright journeys for factory navigation/i18n/report CSV, supplier role boundaries, end-to-end PO dispatch and partial goods receipt through QA hold and traceability, password reset, and invitation acceptance.
- A session-scoped fixture that runs a temporary SQLite database, FastAPI/Uvicorn, and Vite for isolated browser testing.
- Cross-platform one-command runners (`scripts/e2e/run.sh` and `scripts/e2e/run.ps1`) that install backend/E2E Python dependencies, frontend packages and Playwright Chromium.
- GitHub Actions `browser-e2e` job using Python 3.12, Node 22 and Chromium.
- Updated README, testing guide, status and changelog with exact execution scope.

## Verification executed

- Backend: `PYTHONPATH=. pytest -q` from `backend/` — **57 passed**.
- Python compilation: `python -m compileall -q backend/app backend/migrations backend/tests e2e` — passed.
- Browser test discovery: `python -m pytest --collect-only -q e2e` — **5 tests collected**.
- CI workflow YAML parse — passed.
- Docker Compose YAML parse — passed; eight services present.
- `bash -n scripts/e2e/run.sh` — passed.
- Standalone system Chromium launch through Playwright — passed. This verifies the installed browser can start, not that the application journeys pass.

## Not verified

- Actual Playwright browser journeys: not run. `frontend/node_modules` is absent and npm installation failed because the environment could not resolve `registry.npmjs.org` (`EAI_AGAIN`).
- Dependency-backed `tsc -b` and Vite production build: not run for the same reason.
- Docker image builds and Compose runtime: not run; Docker is unavailable.
- PostgreSQL 17 migrations, RLS policies, runtime-role ACLs and concurrency: not run; no PostgreSQL server is available.
- Real SMTP delivery, production deployment, load testing and factory acceptance: not run.

## Run browser acceptance locally

```bash
# Linux/macOS
./scripts/e2e/run.sh

# Windows PowerShell
.\scripts\e2e\run.ps1
```

The runner installs all required Python and npm packages plus Chromium, then executes `python -m pytest -q e2e`. For details and limitations, see `README.md` and `TESTING.md`.
