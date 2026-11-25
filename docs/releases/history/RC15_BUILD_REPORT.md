# FactoryLink RC15 — Production configuration and browser security hardening

**Build:** FactoryLink — Japan Local RC15  
**Date:** 2026-11-03  
**Status:** Final source-hardening candidate for evaluation. Not a production-accepted or certified release.

## RC15 changes

### Production startup fails closed

- Production requires `JWT_ALGORITHM=HS256` and a non-placeholder `JWT_SECRET_KEY` of at least 32 bytes.
- Production requires `DATABASE_URL` to use `postgresql+psycopg` with `sslmode=require`, `verify-ca` or `verify-full`. SQLite, non-Psycopg URLs and plaintext PostgreSQL connections are rejected.
- Production requires exact HTTPS-only `CORS_ORIGINS`; wildcard and HTTP origins are rejected.
- Production requires `SMTP_STARTTLS=true`; SMTP username and password must either both be configured or both be empty.
- Existing production gates remain: no demo seeding, no open registration, no development action-link exposure, non-local SMTP sender and HTTPS frontend URL.

### Browser and edge headers

- Nginx adds a restrictive Content Security Policy to the React application: same-origin defaults/scripts/API connections, no embedded objects or frames, and controlled image/style/font sources.
- The exact `/docs` route remains separate because FastAPI Swagger UI includes an inline initializer; do not expose interactive API docs publicly without access controls.
- Common security headers are emitted for the application and proxied endpoints.
- HSTS is emitted only when the trusted hosting edge supplies `X-Forwarded-Proto: https`; the edge must overwrite client-supplied forwarded-protocol values.

## Checks executed in this environment

| Check | Result |
|---|---|
| Backend regression suite | **83 passed** |
| Python compilation | Passed |
| Fresh SQLite Alembic migration through `0006_supplier_receipt_progress` | Passed |
| Demo seed twice | Passed; stable counts: 3 organisations, 8 users, 2 purchase orders, 3 batches, 3 inventory movements, 2 notifications |
| Live Uvicorn `/health/live` | HTTP 200; request ID returned |
| Live `/metrics` | HTTP 200; Prometheus text returned |
| Factory administrator login | HTTP 200 |
| Factory dashboard | HTTP 200 |
| Supplier login and linked purchase orders | HTTP 200; 2 purchase orders visible |
| Supplier read of factory inventory | HTTP 403 as expected |
| Production configuration regression tests | Passed: unsupported JWT algorithm, no-TLS database URL, SQLite production URL, HTTP/path-bearing CORS origins, disabled SMTP STARTTLS and partial SMTP credentials all rejected |
| Frontend TypeScript/TSX syntax transpilation | Passed for `App.tsx`, `i18n.ts`, `main.tsx` |
| Nginx config syntax | Passed with `backend:8000` substituted to `127.0.0.1:8000` because the Compose DNS name is unavailable outside Docker |
| Docker Compose and GitHub Actions YAML parse | Passed |
| Bash startup, E2E, backup/restore and PostgreSQL acceptance script syntax | Passed |
| k6 script JavaScript syntax | Passed |
| Playwright E2E collection | 5 journeys collected; application journeys not executed |

## Checks not executed / blockers

- Docker image builds and Compose service startup: Docker CLI/daemon is not installed in this runner.
- Actual PostgreSQL 17 role bootstrap, RLS policies, triggers, column grants, concurrency and backup/restore: PostgreSQL server/client tools are not installed. The service-backed `postgresql-acceptance` GitHub Actions job is configured but has not been run in this environment.
- Redis/Celery runtime: Redis server and CLI are unavailable here; readiness requires Redis and previously reported it unavailable.
- Vite production build: `npm run build` was attempted and failed because `frontend/node_modules` is absent (`TS2688: Cannot find type definition file for vite/client`). npm registry access is unavailable/timed out in this environment.
- Playwright browser journeys: five tests collect successfully, but the app journeys require installed frontend dependencies and a running Vite app.
- k6 load workload: k6 is not installed; only the script syntax was checked.
- Windows PowerShell backup/restore parsing: PowerShell 7 is not installed.
- Real backup/restore drill and live production deployment: not executed. No target account, domain, credentials or deployment approval was supplied.
- Independent security, privacy, Japanese business-process and regulatory review: not executed; no certification or statutory-compliance claim is made.

## Release decision

RC15 is the latest source package and closes production transport-configuration and SPA browser-header gaps. It is **not yet FactoryLink 1.0**. Before using real factory/supplier data, complete the gates in `FINAL_ACCEPTANCE_CHECKLIST.md`: real PostgreSQL 17 + Redis acceptance, Docker Compose startup, dependency-backed Vite build, Playwright journeys, backup/restore drill, k6 load test, Windows script validation and independent security review.
