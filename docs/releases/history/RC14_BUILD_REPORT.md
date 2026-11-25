# FactoryLink RC14 — Production Hardening Build Report

**Build:** FactoryLink — Japan Local RC14  
**Date:** 2026-11-03  
**Status:** Local evaluation release candidate. Not production certified.

## RC14 changes

### Observability and health

- Added server-generated `X-Request-ID` correlation IDs.
- Added JSON HTTP access records with request ID, method, route template, status and duration. Request headers, bodies, query strings, passwords and token values are not serialized by the application access logger.
- Added internal Prometheus-format request counters and request-duration totals. Metrics are process-local and are not proxied by the public Nginx frontend; multi-instance deployments must aggregate metrics externally.
- Added `/health/live` as a process liveness probe and `/health/ready` as a database + Redis readiness probe.
- Changed the Docker backend health check and local startup scripts to wait for readiness.

### Backup and recovery tooling

- Added Bash and Windows PowerShell scripts to back up the PostgreSQL database in custom `pg_dump` format and uploaded documents as a separate archive.
- Added SHA-256 manifests, retention control and protected local backup directories on Linux.
- Added explicit, destructive-restore confirmation, archive path checks and pre-restore database/uploads copies.
- Restore scripts stop app traffic services in order, restore uploads without renaming the Docker volume mount point, restore PostgreSQL, reapply the runtime database role/column grants, apply pending Alembic migrations without reseeding demo data, and then restart application services.
- Added `.backups/` to `.gitignore`.

### Load-testing and operations

- Added a k6 localhost-restricted read-path smoke profile for a dedicated account.
- Added backup, restore, health, metrics and load-test documentation.

## Checks executed in this environment

| Check | Result |
|---|---|
| Backend test suite | **73 passed** |
| Python compilation | Passed |
| Fresh SQLite Alembic migration through `0006_supplier_receipt_progress` | Passed |
| Demo seed run twice | Passed; stable counts: 3 organisations, 8 users, 1 supplier, 2 purchase orders, 3 batches, 3 movements, 2 notifications |
| Live Uvicorn `/health/live` | HTTP 200; server-generated request ID present |
| Live `/health/ready` | HTTP 503 with `database=ok`, `redis=unavailable` (this runner has no Redis Python client/server) |
| Live `/metrics` | Prometheus text returned |
| Factory administrator login | HTTP 200 |
| Factory dashboard | HTTP 200 |
| Bash backup/restore/start script syntax | Passed (`bash -n`) |
| Backup + restore shell orchestration with a mocked Docker Compose CLI | Passed: archive creation/checksum, pre-restore copies, safe upload-volume content replacement and role-bootstrap/migration/restart command flow; **not** a real Docker/PostgreSQL drill |
| k6 smoke-script JavaScript syntax | Passed (`node --check`) |
| Docker Compose and CI YAML parse | Passed |
| Nginx configuration syntax | Passed using an HTTP-context wrapper and local upstream substitution because the Docker `backend` DNS name is unavailable outside Compose |

## Checks not executed / blockers

- Docker Compose image builds and service startup: Docker CLI/daemon are not installed in this runner.
- Actual PostgreSQL 17 role bootstrap, RLS, trigger, backup and restore: PostgreSQL client/server tools are not installed. The RC12 PostgreSQL + Redis CI job remains the route to execute these checks on a service-enabled runner.
- Redis/Celery runtime and readiness success: Redis server/client are unavailable here; readiness correctly reported Redis unavailable.
- Vite production build: `npm run build` was attempted and failed because `frontend/node_modules` is absent (`TS2688: Cannot find type definition file for vite/client`). Dependency installation previously timed out while reaching the npm registry.
- Playwright browser journeys: dependencies and running Vite app are not available, so only the earlier suite collection is known; no RC14 browser journeys were executed.
- k6 load profile: k6 is not installed, so the workload was not executed.
- PowerShell script parsing: `pwsh` is not installed, so Windows backup/restore scripts require validation on Windows PowerShell 7.
- Real backup/restore functional drill: not run because Docker/PostgreSQL are unavailable. The mocked Compose-command exercise only validates host-side script orchestration and archive handling. Backup archives are not encrypted by these scripts; protect the backup directory with encrypted storage and access controls.

## Local commands

Linux/macOS:

```bash
./scripts/backup/backup.sh
./scripts/backup/restore.sh .backups/factorylink-YYYYMMDDTHHMMSSZ --confirm
```

Windows PowerShell:

```powershell
.\scripts\backup\backup.ps1
.\scripts\backup\restore.ps1 -BackupDirectory .backups\factorylink-YYYYMMDDTHHMMSSZ -ConfirmRestore
```

k6 smoke test (after the stack is running, using a dedicated local test account):

```bash
LOAD_TEST_EMAIL=load-test@factorylink.local LOAD_TEST_PASSWORD='change-this-test-password' k6 run scripts/load/k6-smoke.js
```

**Release decision:** RC14 adds useful operational hardening and passes the checks listed above, but it is not a production release. Complete real PostgreSQL/Redis/Docker acceptance, frontend dependency-backed build, Playwright browser journeys, backup/restore drill, k6 test, Windows script validation and independent security review before FactoryLink 1.0.
