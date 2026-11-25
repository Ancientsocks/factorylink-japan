# FactoryLink RC18 Build Report

**Release:** `1.0.0-rc.18`  
**Date:** 2026-11-03  
**Status:** Local evaluation candidate; production acceptance remains open.

## RC18 changes

- Added a one-time operator-only bootstrap for the first Japanese manufacturer workspace and `ORG_ADMIN` user. It has no public HTTP endpoint or default password, enforces a unique 14+ character password, writes an audit event, and refuses to run on a non-empty database.
- Added a PostgreSQL transaction-scoped advisory lock around the first-admin empty-database check and creation so concurrent operator commands cannot initialise separate first tenants.
- Added a Render-managed runtime-credential deployment path. The deployment helper validates the managed PostgreSQL role, rejects cluster-level privileges and role memberships, applies the reviewed table/column/sequence grants without `CREATE ROLE` or `ALTER ROLE`, and runs migrations with the separately supplied owner URL.
- Added a Render Blueprint for private FastAPI, public Docker/Nginx frontend, PostgreSQL 17, private Key Value, Celery worker and scheduler services.
- Documented the initial database provisioning order, managed credential rotation behaviour, one-time administrator bootstrap and remaining acceptance gates.

## Local verification performed

| Check | Result |
|---|---|
| Backend regression suite | **98 passed** |
| Python compile check | Passed |
| Fresh Alembic migration | Passed (SQLite portability path) |
| Demo seed first run | Passed |
| Demo seed idempotency | Passed (second run) |
| Live Uvicorn API smoke | Passed |
| Full live manufacturing workflow | Passed: factory PO, supplier confirmation/dispatch, linked receipt, supplier-visible receipt total, production completion, failed inspection, batch hold and traceability |
| Render Blueprint YAML parse and cross-service references | Passed (static parse/assertions only) |

The reproducible acceptance run is saved in `RC18_ACCEPTANCE_RESULTS.json`: **6 passed, 0 failed, 5 skipped**.

## Explicitly unverified

This environment does not have a Docker daemon, PostgreSQL server, Redis server or installed frontend dependencies; npm registry access has also failed. Therefore the following have **not** passed:

- Docker Compose configuration opt-in and isolated Docker runtime.
- PostgreSQL 17 RLS, triggers and runtime ACL integration tests.
- Redis and Celery service execution.
- Dependency-backed Vite production build.
- The five Playwright browser journeys.
- Render CLI/schema validation, Blueprint sync or live deployment.
- Real backup/restore drill, load test against an isolated stack, and independent security review.

RC18 is not production-certified and must not be used with real factory data until the outstanding release gates are run and accepted in a controlled environment.
