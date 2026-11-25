# FactoryLink RC13 Build & Verification Report

**Build:** FactoryLink — Japan Local RC13  
**Date:** 2026-11-03  
**Status:** Local evaluation release candidate; not production certified.

## RC13 changes

- Added `GET /api/v1/notifications/unread-count` with organisation-scoped aggregation.
- Added `PATCH /api/v1/notifications/read-all`, updating only unread rows owned by the authenticated organisation.
- Added live unread counts to the sidebar and header bell, notification preview mark-read actions, and a full notification view with All / Unread only / Needs attention filters.
- Added inventory CSV/XLSX exports containing lot, on-hand, reserved, available, unit cost and computed JPY stock valuation.
- Added quality CSV/XLSX exports containing inspection, product, linked lot, result, defects, sample size, calculated defect rate and corrective action.
- Added three bilingual report cards in the React Reports page and dataset-specific download file names.
- Supplier accounts are explicitly denied inventory and quality manufacturer report endpoints. Text columns are escaped for CSV/XLSX formula safety, and XLSX export strings use explicit text cell types.
- Added tenant-boundary, bulk-read, formula-safety, report calculation, CSV/XLSX and supplier-denial regression tests.

## Checks executed in this environment

| Check | Result |
|---|---|
| Backend tests | **68 passed** |
| Python compilation | Passed |
| Fresh SQLite Alembic migration through `0006` | Passed |
| Demo seed twice | Passed; stable counts |
| Live Uvicorn API smoke | Passed: login, unread count, inventory CSV, quality XLSX, read-all, updated unread count, supplier export denial |
| Frontend TS/TSX syntax transpilation | Passed; zero syntax diagnostics in 3 source files |
| Limited local tsc compatibility check (temporary React/lucide declarations; noImplicitAny disabled) | Passed; not a substitute for real package build |
| Playwright E2E collection | 5 browser journeys collected |
| Python/shell/Compose/CI YAML checks | Passed |

## Not executed here

- Dependency-backed `npm run build` / Vite production bundle: `npm install` timed out; no `frontend/node_modules` exists.
- Actual Playwright browser journeys: dependencies and Vite app runtime are unavailable; only test collection was performed.
- Docker image builds and Compose startup: Docker CLI/daemon unavailable.
- PostgreSQL 17 migration, RLS, trigger and runtime-role ACL acceptance: no PostgreSQL server/client available.
- Redis/Celery service runtime, SMTP delivery, production deployment and customer acceptance.

The existing PostgreSQL 17 + Redis and browser CI jobs remain configured in `.github/workflows/ci.yml`; their successful execution is still required before those acceptance gates can be marked complete.

## Local run

1. Extract the ZIP.
2. Install and start Docker Desktop.
3. Open PowerShell in the `FactoryLink` directory.
4. Run `.\scripts\start.ps1`.
5. Open `http://localhost:8080`.

Demo credentials are for local evaluation only. Change credentials and secrets, disable demo seeding/public registration, configure HTTPS and SMTP, and complete PostgreSQL/browser/security acceptance before external deployment or real factory data.
