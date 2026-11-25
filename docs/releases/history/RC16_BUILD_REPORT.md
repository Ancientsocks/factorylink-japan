# FactoryLink RC16 — Reproducible acceptance runner

**Build:** FactoryLink Japan Local RC16 (`1.0.0-rc.16`)  
**Date:** 2026-11-03  
**Status:** Acceptance tooling release candidate. Not a production-accepted release.

## RC16 changes

- Added `scripts/acceptance/run.py`, a cross-platform Python runner for backend tests, Python compilation, a clean Alembic migration, two consecutive demo-seed runs and live API authorization/report smoke tests.
- The runner distinguishes `PASS`, `FAIL` and `SKIP`. Missing infrastructure is never counted as a pass. `--strict` returns non-zero when optional acceptance gates are skipped.
- Added opt-in Docker Compose config, Vite production build, Playwright, and PostgreSQL/Redis/Celery gates.
- Added a dedicated GitHub Actions `local-acceptance` job and JSON result artifact.
- Fixed the runner's response-header normalization and readiness-poll backoff after its initial smoke attempt exposed a case-sensitive header lookup.
- Redacted the demo password from subprocess output before writing acceptance result reports.

## Executed acceptance run

Command:

```bash
python scripts/acceptance/run.py --report /tmp/factorylink-rc16-acceptance.json
```

Result: **6 passed, 0 failed, 4 skipped**.

| Check | Result |
|---|---|
| Backend regression suite | **86 passed** |
| Python compile check | Passed |
| Fresh Alembic migration through head | Passed |
| Demo seed first run | Passed |
| Demo seed idempotency (second run) | Passed |
| Live API factory/supplier smoke | Passed |
| Docker runtime/Compose validation | Skipped — Docker CLI/daemon unavailable |
| Vite production build | Skipped — frontend dependencies absent; npm install timed out |
| Playwright application journeys | Skipped — frontend dependencies absent |
| PostgreSQL 17 / RLS / Redis / Celery acceptance | Skipped — PostgreSQL and Redis services/tools unavailable |

The live API smoke started Uvicorn on an ephemeral local port and verified:

- `/health/live` returned HTTP 200 and a request ID.
- `/metrics` returned Prometheus request counters.
- Factory demo administrator login and dashboard returned HTTP 200.
- Factory inventory CSV contained seeded lot data.
- Supplier login returned HTTP 200 and the linked purchase-order list contained two orders.
- Supplier access to manufacturer inventory and inventory reports returned HTTP 403.

The exact JSON output from the executed run is included as `RC16_ACCEPTANCE_RESULTS.json`.

## CI changes

Added `local-acceptance` to `.github/workflows/ci.yml`. It installs backend requirements, runs the acceptance runner (the backend suite is already run in the separate backend job), and uploads the JSON report as an artifact. Existing dedicated frontend, browser E2E and PostgreSQL/Redis jobs remain separate.

## Limitations

- `npm install --no-audit --no-fund --prefer-offline` was attempted in `frontend/` but timed out. No dependency-backed Vite build was possible; no successful npm package resolution is claimed.
- Docker CLI/daemon, PostgreSQL server/client and Redis server are not present in this runtime. Compose service startup, PostgreSQL RLS/ACL/trigger execution, Celery worker execution through Redis, and actual backup/restore drills are not verified.
- The five Playwright tests remain collected by the E2E suite but were not run against the web app because Vite dependencies are unavailable.
- k6 load execution and PowerShell validation remain outstanding.

## Release decision

RC16 improves repeatability and evidence capture; it does not close FactoryLink 1.0 acceptance. Use `python scripts/acceptance/run.py` for the local checks. Before go-live, rerun with all prerequisites and flags `--with-docker-config --with-frontend-build --with-browser-e2e --with-postgres --strict`, complete load and backup/restore testing, and obtain independent security and customer acceptance reviews.
