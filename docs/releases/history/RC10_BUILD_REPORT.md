# FactoryLink RC10 — Build and Verification Report

**Date:** 2026-11-03  
**Release:** Japan Local RC10  
**Purpose:** Milestone 10 source-integration hardening and local API verification.

## Changes in RC10

1. Fixed an actual frontend compile blocker in the inventory-receipt modal: it referenced `purchaseOrders` and `setPurchaseOrders` without declaring component state.
2. Added release-integrity backend tests for that modal contract, fixed frontend API paths vs. FastAPI route definitions, and the Compose owner/runtime database split.
3. Fixed the PostgreSQL runtime-role bootstrap so an ordinary Compose restart cannot re-grant broad table-level writes.
4. Reapplied only explicitly reviewed workflow-column `UPDATE` privileges after the broad table revoke, conditionally for tables already created. This is needed because PostgreSQL's table-level `REVOKE UPDATE` also removes corresponding column-level update grants.
5. Re-locked `alembic_version` after the bootstrap's global `SELECT`/`INSERT` grant.
6. Expanded `verify-runtime-role.sql` to fail on unsafe role flags, missing required workflow column grants, excessive purchase-order update access, mutable audit history, deletes, or migration-history writes.

## Checks actually executed

| Check | Result |
|---|---|
| Backend pytest suite | **56 passed** |
| Python compilation | Passed |
| Fresh Alembic migration through `0005_account_lifecycle` on SQLite | Passed |
| Demo seed executed twice on a fresh database | Passed; no duplicate demo records |
| Live Uvicorn `/health` | HTTP 200 |
| Factory demo login and dashboard | HTTP 200; 3 sample production orders |
| Supplier demo login and linked purchase orders | HTTP 200; 2 linked orders |
| Live OpenAPI schema | 36 paths |
| Frontend fixed API path contract | Passed |
| Strict TypeScript semantic check with temporary declarations | Passed; no diagnostics |
| TypeScript TSX source transpilation | 3 source files passed |
| Compose YAML | Parsed; expected 8 services and owner/runtime DB URL separation present |
| Linux startup shell syntax | Passed |
| Runtime-role SQL static contract | Passed; explicit column grants and Alembic lock present |

The strict TypeScript check used temporary ambient declarations because frontend npm packages could not be installed here. It is a useful source-level check, but it is **not** the real dependency-backed `tsc -b` and Vite build.

## Not executed / not claimed

- Docker Compose container startup or image builds: Docker CLI/daemon is not installed in this environment.
- PostgreSQL 17 migration, RLS policy, role and column privilege acceptance: no PostgreSQL server/client is installed. SQLite is not a substitute for validating RLS or PostgreSQL ACL behavior.
- Vite production build or browser E2E tests: `npm ping` failed with `EAI_AGAIN` while resolving `registry.npmjs.org`.
- Real SMTP delivery, hosted deployment, load test or independent security review.

## Milestone 10 status

**Partially completed — source integration fixed and local API smoke verified.** Milestone 10 is not fully accepted until a clean target machine completes `docker compose up --build`, the PostgreSQL migration and seed, `verify-runtime-role.sql`, `verify-rls.sql`, the real `npm run build`, and core browser workflows.

## Local validation commands

Backend tests:

```bash
cd backend
python -m pytest -q
python -m compileall -q app migrations tests
```

Container stack on a host with Docker Desktop/Compose:

```powershell
# Windows PowerShell from the project root
.\scripts\start.ps1
```

PostgreSQL acceptance after Compose startup (run from the project root using the documented `docker compose exec` procedure in `DEPLOYMENT.md`):

```bash
psql -v runtime_db_user="$RUNTIME_DB_USER" -f scripts/db/verify-runtime-role.sql
psql -v runtime_db_user="$RUNTIME_DB_USER" -f scripts/db/verify-rls.sql
```

Frontend build on a host with npm registry access:

```bash
cd frontend
npm install
npm run build
```
