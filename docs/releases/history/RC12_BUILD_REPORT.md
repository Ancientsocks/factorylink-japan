# FactoryLink RC12 Build & Verification Report

**Build:** FactoryLink — Japan Local RC12  
**Date:** 2026-11-03  
**Status:** Local evaluation package; not production certified.

## RC12 changes

- Persisted the factory-confirmed cumulative receipt quantity on `purchase_orders` so linked suppliers can view partial-delivery progress without SELECT access to factory inventory batches or movement ledgers.
- Added migration `0006_supplier_receipt_progress` to add/backfill the receipt counter from immutable receipt movements, enforce `0 <= received_quantity <= quantity`, ensure a database-side default exists on fresh and upgraded installs, and add a PostgreSQL trigger requiring the PO-owning factory tenant context for counter changes.
- Tightened supplier PO RLS to require both the supplier directory record and PO to belong to the same factory organisation.
- Extended the PostgreSQL live API acceptance to create a PO as the factory, submit it, confirm/dispatch it as the supplier, record a partial receipt as the factory runtime role, and verify supplier-visible cumulative and remaining quantities.
- Added a PostgreSQL 17 + Redis CI service job that applies migrations, seeds demo data, repeats least-privilege bootstrap, executes RLS/ACL checks, starts API as the restricted role, and runs a tenant-aware Celery task.
- Corrected raw RLS acceptance SQL inserts to explicitly provide required fields rather than relying on Python-only defaults.

## Checks executed in this environment

| Check | Result |
|---|---|
| Backend API and release-integrity tests | **64 passed** (`PYTHONPATH=. python -m pytest -q` from `backend/`) |
| Python bytecode compilation | Passed (`compileall` for backend, migrations, E2E and DB scripts) |
| Shell script syntax | Passed (`bash -n` for acceptance, startup and E2E scripts) |
| CI workflow YAML | Parsed; jobs: backend, frontend, browser E2E, PostgreSQL acceptance |
| Docker Compose YAML | Parsed; eight configured services |
| E2E test discovery | Five Playwright browser journeys collected |
| Clean SQLite migration | Passed through `0006_supplier_receipt_progress` |
| Clean demo seed | Passed twice without duplicating records |
| Database default | Confirmed `received_quantity` has SQL-level default `0` on a fresh install |
| Missing-default repair path | Passed by resetting a validation DB to revision `0005` and applying `0006`; SQL default was repaired |
| RC11 populated SQLite upgrade | Passed through `0006`; historical receipt totals backfilled to 3,200 and 1,500 for the two demo POs |
| Live Uvicorn API smoke against seeded SQLite | Passed: factory dashboard/inventory, supplier PO visibility, supplier inventory denial, PO create/submit/confirm/dispatch/partial receipt, supplier-visible 2-of-5 receipt progress, refresh rotation, language update and post-commit context |
| ZIP archive integrity | Verified with `unzip -t` |

## Not executed here

This runner has no Docker/Podman daemon, PostgreSQL server/client binaries, Redis server or PostgreSQL driver. Frontend `node_modules` are also absent, and prior npm registry access failed on DNS resolution. Therefore these checks are **not** marked passed:

- PostgreSQL 17 migration/runtime execution, RLS policies, trigger behavior and column-level ACLs.
- Restricted-role PostgreSQL API smoke (the same smoke logic was run only against SQLite here).
- Redis/Celery worker and scheduler runtime.
- Docker image builds and Compose service startup.
- Dependency-backed `npm run build` / Vite production output.
- The five Playwright application browser journeys.
- SMTP delivery, production deployment and real customer acceptance.

The PostgreSQL 17 + Redis acceptance workflow is configured in `.github/workflows/ci.yml` and can execute on a GitHub Actions runner with service containers. A green CI result is still required before PostgreSQL security and worker acceptance can be marked complete.

## Local run

1. Extract the ZIP.
2. Install Docker Desktop and start it.
3. Open PowerShell in the `FactoryLink` directory.
4. Run `.\scripts\start.ps1` (PowerShell) or `bash scripts/start.sh` (macOS/Linux).
5. Open `http://localhost:8080`.

Default demo accounts are for local evaluation only. Change all demo passwords, rotate secrets, disable demo seeding/public registration and configure SMTP before any external deployment. Do not load real production or customer data until the PostgreSQL acceptance and independent security review are complete.
