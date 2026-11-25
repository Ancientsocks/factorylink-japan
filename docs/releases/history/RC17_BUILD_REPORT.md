# FactoryLink RC17 — Live workflow and isolated Docker acceptance

**Build:** FactoryLink Japan Local RC17 (`1.0.0-rc.17`)  
**Date:** 2026-11-03  
**Status:** Improved local evaluation candidate. Not a production-accepted release.

## RC17 changes

- Extended `scripts/acceptance/run.py` to execute the complete operational workflow through a live Uvicorn server, not just login/dashboard checks.
- The live flow creates and submits a factory purchase order, has the linked supplier confirm and dispatch it, records a factory goods receipt against that exact PO, verifies supplier-visible cumulative receipt progress, creates a material-backed production order, reserves and consumes stock through valid states, records a failed quality inspection, verifies batch hold, and checks the traceability timeline.
- Uses a dedicated acceptance material and deterministic identifiers inside a disposable migrated/seeded SQLite database. Seed demo records are not modified.
- Added `--with-docker-runtime`: an isolated Compose project with a unique project name, free host port, temporary volumes, build/start/readiness checks, Nginx SPA and Swagger checks, factory/supplier API checks and automatic `down --volumes --remove-orphans` cleanup for only that isolated project.
- Added a dedicated `docker-compose-runtime` GitHub Actions job so the full eight-service stack is exercised on a Docker-enabled CI runner.
- Added release-integrity regression tests for the live business workflow and Docker runtime gate.

## Verification executed

Command:

```bash
python scripts/acceptance/run.py --with-docker-config --with-docker-runtime --with-frontend-build --with-browser-e2e --with-postgres --report RC17_ACCEPTANCE_RESULTS.json
```

Result: **6 passed, 0 failed, 5 skipped**.

| Check | Result |
|---|---|
| Backend regression suite | **88 passed** |
| Python compile check | Passed |
| Fresh Alembic migration | Passed |
| Demo seed first run | Passed |
| Demo seed idempotency (second run) | Passed |
| Live API factory/supplier full workflow | Passed |
| Docker Compose configuration parse | Skipped — Docker CLI not installed |
| Isolated Docker Compose build/runtime | Skipped — Docker CLI/daemon not installed |
| Vite production build | Skipped — frontend dependencies unavailable; npm install timed out |
| Playwright application journeys | Skipped — frontend dependencies unavailable |
| PostgreSQL 17 / RLS / Redis / Celery acceptance | Skipped — PostgreSQL and Redis services/tools unavailable |

Additional static checks: Compose and GitHub Actions YAML parsed; all eight Compose services were identified; five Playwright journeys were collected; Bash scripts passed syntax checks; k6 script passed Node syntax check; four frontend TypeScript/TSX source files transpiled with zero syntax diagnostics using TypeScript 5.8.3. These do not replace a dependency-backed Vite build or a browser execution run.

### Live API workflow detail

- Factory administrator login, dashboard and inventory report returned expected responses.
- Supplier login returned linked purchase orders; manufacturer inventory and report endpoints returned 403.
- Factory created/submitted `PO-ACCEPTANCE-LIVE-001` for 12 kg of `Acceptance Alloy`.
- Supplier confirmed and dispatched the order.
- Warehouse recorded `LOT-ACCEPTANCE-LIVE-001` against that PO.
- Supplier-visible progress showed 12/12 kg received and `DELIVERED` status.
- Factory created/completed a production order that reserved and consumed 4 kg.
- Quality inspector recorded a failed inspection with corrective action.
- The batch ended in `HOLD`; traceability contained goods receipt, production reservation, production consumption and quality hold events.

The exact machine-readable results are included as `RC17_ACCEPTANCE_RESULTS.json`.

## Environment limitations

- Docker CLI/daemon, PostgreSQL server/client and Redis server are not installed in this runtime. No Docker container startup or PostgreSQL RLS/ACL/trigger/Redis/Celery runtime execution is claimed.
- The frontend has no `node_modules` or npm cache. An npm install attempt timed out, so no dependency-backed project type-check or Vite production build is claimed.
- Five Playwright application journeys are discoverable (`5 tests collected`) but were not executed because the frontend development server cannot start without the missing dependencies.
- Actual PostgreSQL backup/restore and k6 load testing remain outstanding.
- The Docker runtime job is configured in `.github/workflows/ci.yml`, but no remote GitHub Actions result was available in this session.

## Release decision

RC17 improves evidence for the live business workflow and adds the missing isolated Compose runtime acceptance gate. It does not close FactoryLink 1.0 acceptance. Before go-live, pass the Docker runtime CI job, PostgreSQL 17 RLS/ACL/trigger and Redis/Celery acceptance, npm/Vite production build, Playwright browser journeys, real backup/restore and load tests, and obtain independent security and factory-customer acceptance reviews.
