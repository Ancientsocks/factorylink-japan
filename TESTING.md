# Testing

## Current code-level verification — 2026-11-23

Environment: Windows, Python 3.12.12 (`.venv`), Node 24.19.0. Docker Desktop
was not running, so container and live-service gates were not attempted.

| Check | Command | Result |
|---|---|---|
| Backend regression | `python -m pytest -q` (from `backend/`) | **198 passed**, 1 upstream Starlette/httpx deprecation warning |
| Google sign-in | `python -m pytest -q tests/test_google_auth.py` (from `backend/`) | **9 passed** (configuration gate, signed state, failed exchange, single-use hand-off, existing-user sign-in, Google workspace sign-up, taken organisation code, inactive account, registration switch) |
| Email delivery | `python -m pytest -q tests/test_email_delivery.py` (from `backend/`) | **7 passed** (channel selection, SMTP precedence, no-provider error, direct send, failure reporting, HTML body) |
| Email verification | `python -m pytest -q tests/test_email_verification.py` (from `backend/`) | **12 passed** (code issue/verify, attempts, expiry, resend cooldown, purpose scoping, no account enumeration, development-only code display, ticket required for register/reset) |
| Record edit/delete rules | `python -m pytest -q tests/test_crud_operations.py` | **15 passed** (permissions, mutable-state guards, referential integrity, audit entries) |
| Python compile | `python -m compileall -q app migrations tests` | passed |
| Backend dependency audit | `pip-audit -r backend/requirements.txt` | **no known vulnerabilities** |
| Frontend unit tests | `npm test` (from `frontend/`) | **8 passed** (2 files) |
| Frontend production build | `npm run build` | passed, 1,580 modules, Vite 7.3.8 |
| Frontend dependency audit | `npm audit --audit-level=high` | **0 vulnerabilities** |
| Local acceptance runner | `python scripts/acceptance/run.py --skip-backend-tests` | **5 passed, 0 failed, 6 skipped** |
| Live email-code flows (2026-11-23) | `curl` against the local dev API, plus the browser sign-up and forgot-password screens | request code → verify → register → sign in, then reset code → confirm → sign in with the new password: all passed. Real SMTP delivery was not exercised. |
| Google hand-off flows (2026-11-23) | `curl` and the browser against the local dev API with simulated Google hand-off codes | existing account sign-in, new-account workspace form and creation, back buttons, resend countdown: all passed. The redirect to and from Google itself was not exercised (no Google client ID); `/api/v1/auth/google/start` returns 503 until credentials are configured. |

The acceptance runner's skips are the Docker Compose configuration/runtime,
Vite build, Playwright and PostgreSQL/Redis/Celery gates. They were not run.


## Current local and isolated-staging verification — 2026-11-05

The earlier Docker Linux-engine pipe failure was resolved later in the same
work session. The current local stack is running with Alembic revision
`0011_inventory_reconciliation`; backend and frontend health checks passed,
and the database/uploads volumes were retained. See `PROJECT_STATUS.md` for
the complete current status.

- Full backend regression before this packaging pass: **152 passed**.
- Current package-focused Render/release-integrity regression: **51 passed**.
- Current source Python compilation and frontend TypeScript project check
  passed; this packaging environment could not repeat the full dependency-backed
  backend or Vitest/build suites.
- Isolated staging browser journeys: **3 passed**.
- PostgreSQL workflow, Redis throttling/isolation/expiry, migration rollback and
  retry, backup/restore into a separate database, and a bounded five-user load
  smoke test passed. The load run is preliminary and does not establish capacity.
- Real SMTP delivery remains unconfigured; the Celery retry/terminal-failure
  path was verified instead.
- Render deployment, private S3 acceptance, external backup/PITR, external
  monitoring/alert delivery, Japanese customer privacy approval and factory
  acceptance remain outstanding.

## Earlier Docker outage record — superseded

- Read-only probe `docker compose ps --all`: **BLOCKED**. Docker CLI could not
  connect to `npipe:////./pipe/dockerDesktopLinuxEngine`; Windows returned
  “The system cannot find the file specified.”
- Container, image, Compose-project, volume, and current development database
  inventory therefore could not be collected. No staging project was created,
  and no existing container, database, or volume was started, stopped, or
  modified.
- No migration, readiness, PostgreSQL/RLS, Redis, browser-on-staging,
  backup/restore, load, resource-usage, or live Celery test was run. No
  throughput, latency, or database resource measurements are available.
- The engine being unavailable is the exact external blocker. Restart/enable
  Docker Desktop's Linux engine, then repeat read-only inventory before any
  staging action. The prior reported backend image revision `0008` versus
  database revision `0009` remains unresolved.

## Earlier pre-recovery continuation snapshot — superseded

- Corrected reconciliation lock order, hardened reminder-task redelivery and
  added focused idempotency coverage.
- Added PostgreSQL scripts for all-table RLS/runtime-role checks, Redis
  throttling/expiry/isolation, concurrent inventory updates, and migration
  failure/recovery from empty and prior-revision databases.
- Added a bounded, paced manufacturing/inventory/dashboard staging load test.
- Full backend regression: `python -m pytest -q -o pythonpath=backend
  backend\tests` — **152 passed**, 1 upstream Starlette/AnyIO deprecation
  warning (181.39 seconds).
- Docker-dependent staging/image inspection and live PostgreSQL, Redis,
  migration, backup/restore, and load tests: **not run**. Docker Desktop's
  Linux-engine named pipe was unavailable, so no containers or image IDs could
  be inspected and no staging resources were created. The reported `0008`
  backend image / `0009` database mismatch remains unresolved.
- No existing database records or Docker volumes were intentionally changed.

See [PROJECT_STATUS.md](./PROJECT_STATUS.md) for per-task implementation
statuses and [PRODUCTION_OPERATIONS_RUNBOOK.md](./PRODUCTION_OPERATIONS_RUNBOOK.md)
for isolated execution procedures.

## Production-readiness review — 2026-11-04

The review updated the audit, first-administrator deployment procedure,
operations monitoring prerequisites, CI production Compose validation/image
build job, and repeatable VS Code tasks.

- Production Compose static render with `.env.production.example`:
  **PASS**; no services were started.
- Production backend and frontend image builds:
  **PASS**. The frontend image executed `npm ci` and `npm run build`.
  Neither image was started or deployed.
- Backend suite: **140 passed**, 1 upstream Starlette/AnyIO deprecation
  warning (178.09 seconds). The first run exposed a stale assertion expecting
  `npm install`; the assertion now checks the Dockerfile's lockfile-based
  `npm ci` and the lockfile's presence. The full suite passed on rerun.
- Frontend unit tests: **8 passed** across 2 files (Vitest 3.2.4).
- Browser acceptance: **5 passed** (75.25 seconds) using the E2E fixture's
  isolated temporary SQLite database.
- PostgreSQL migration/RLS, restricted runtime role, Redis/Celery,
  dependency/security scans, backup/restore drill, load test, and staging
  deployment: **NOT RUN / NOT VERIFIED** in this review.
- No production deployment was started. No existing database or Docker volume
  was deleted, recreated, or restored over. The filled local `.env` was not
  read.

The earlier PostgreSQL workflow/RLS results below remain historical acceptance
evidence; they were not rerun in this review. The CI workflow itself still
requires a successful hosted run. See
[PRODUCTION_READINESS_AUDIT.md](./PRODUCTION_READINESS_AUDIT.md) for the
unresolved release gates.

## Final acceptance follow-up — finished-product quality traceability (2026-11-04)

Results from the final regression run:

- Backend: `python -m pytest -q -o pythonpath=backend backend\tests` — **139 passed**, 1 upstream Starlette/AnyIO deprecation warning (237.09 seconds).
- Frontend unit tests: `npm --prefix frontend run test` — **8 passed** across 2 files using Vitest 3.2.4, React Testing Library, user-event and jsdom.
- Frontend production build/typecheck: `npm --prefix frontend run build` — **passed** (`tsc -b`; Vite transformed 1,580 modules).
- Browser acceptance: `python -m pytest -q -o pythonpath=backend e2e` — **5 passed** (53.19 seconds). A stale “Product” label locator was narrowed to the product textbox after the added finished-batch/serial fields made it ambiguous.
- PostgreSQL 17 API workflow: **passed** against the existing database and restricted `factorylink_app` role. It exercised supplier/PO/receipt, inventory, receiving inspection, reservation/consumption, finished-batch and serial inspections, failure quarantine, CAPA transition guards, source-material hold blocking finished-batch release, controlled source and finished-product release, shipment, forward/backward genealogy, insufficient stock, duplicate/excess receipts, invalid transitions and cross-organisation denials.
- Additive migration: **passed**; database revision is `0009_finished_product_quality`.
- PostgreSQL tenant RLS: **passed** for the new finished-product batch table with missing, factory and second-factory tenant contexts. The verification transaction rolled back its test inserts.
- PostgreSQL runtime-role verification: **passed**; the finished-batch status update grant is present and Alembic writes remain denied.
- Redis/Celery were **not rerun in this feature-specific regression**. The previous 2026-11-04 acceptance run recorded Redis `PONG`, worker/task registration and successful maintenance reminder execution (`notifications_created: 0`).

The PostgreSQL API workflow writes uniquely suffixed acceptance records to the existing database; they were not cleaned up. The additive migration and verification transaction preserved existing rows. No database or Docker volume was deleted or recreated.

The current-source migration and API were run in temporary Compose containers with the workspace backend mounted; those containers were removed after testing and no image was rebuilt. The long-running backend and frontend images were not rebuilt or restarted. Consequently, the existing backend image still contains migration code only through `0008`; its `alembic current` command cannot recognize database revision `0009`. Deploying this code to the long-running stack requires updating its backend/migration images. The acceptance API workflow used the current workspace source and passed against the migrated PostgreSQL database.

Finished-product inspections now support batch-level and optional serial-level references. Failed inspections hold the finished batch, quarantine available serials and open a linked CAPA. Release requires the latest passing documented inspection and rejects release while any source material lot remains on hold. Inspection and CAPA history is present in forward and backward traceability; material-batch inspection remains supported.

### Frontend unit tests

Vitest uses jsdom and React Testing Library. Current tests cover successful and rejected authentication, supplier navigation permissions, persisted Japanese/English switching, dashboard KPI rendering, purchase-order form validity/numeric payloads, API validation errors, localized workflow labels and finished-product serial inspection submission.

```bash
npm --prefix frontend run test
npm --prefix frontend run build
```

### Real PostgreSQL workflow

`scripts/db/postgres-api-smoke.py` is the live API workflow test. The normal PostgreSQL/Redis/Celery runner executes it after migration and seeding. To run it against a running Compose stack, copy it into the backend container and execute it with `FACTORYLINK_BASE_URL=http://backend:8000`. It creates unique records in the configured database and does not roll them back.

These results are acceptance-test evidence only; they are not production certification. Backup/restore, load, customer/staging acceptance, and an independent security review remain separate gates.

## RC23 verification record (2026-11-03)

- Regression groups run in this packaging session: **59 passed** across release-integrity, admin-bootstrap, Render configuration, mailer, malware-scanner and object-storage tests.
- RC22 core-workflow regression cases rerun in this session: **3 passed** (inspection template/CAPA lifecycle, production serial/QR/shipment genealogy, and maintenance downtime analytics).
- Python compilation, fresh SQLite Alembic migration through `0007_quality_capa_serial_traceability`, repeatable demo seeding and the live factory/supplier workflow passed.
- Acceptance runner: **5 passed, 0 failed, 6 skipped** when invoked with `--skip-backend-tests`; the six skips were explicitly infrastructure/build checks not run in this environment.
- Docker image build/runtime, npm/Vite build, Playwright browser journeys, live PostgreSQL/Redis/Celery, ClamAV/S3 runtime and production operations were not run here.

## Backend unit/API tests

The backend test fixture creates a separate in-memory SQLite database for each test. It overrides the application database dependency and does not call the production database.

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app migrations tests
```

Current included tests cover:

- Health and authentication.
- Refresh-token rotation, replay detection, revocation of active descendants in the replayed login family, and preservation of independent login sessions.
- Tenant scoping for inventory.
- Duplicate lot receipt rejection.
- Reason-coded stock adjustments are written to the inventory ledger and cannot reduce stock below existing reservations.
- Insufficient material reservation rejection.
- A quality hold applied after material reservation blocks subsequent production consumption.
- Failed inspection corrective-action requirement and batch hold.
- Supplier visibility scoped to all purchase orders linked to its supplier organisation.
- Supplier users and supplier administrators cannot access factory inventory endpoints; supplier administrators can manage only users in their own supplier organisation.
- Registration creates a manufacturer `ORG_ADMIN` or supplier `SUPPLIER_ADMIN` owner with a hashed password; public registration can be disabled and is rejected without creating a tenant.
- Duplicate organisation codes are rejected.
- A factory can link a supplier workspace by the supplier's company code.
- Inspection defect counts cannot exceed the inspected sample size.
- Maintenance downtime totals remain stable when a completion update is retried.
- Production, inventory and quality CSV/XLSX reports are tenant-scoped and downloadable; inventory/quality exports are denied to supplier accounts and protect formula-like text.
- Notification unread-count and bulk mark-all-read operations are scoped to the authenticated organisation.
- End-to-end API workflow: supplier confirms and dispatches a PO, factory records a linked partial receipt, production reserves and consumes FIFO stock, quality fails the lot, and traceability preserves each event.
- PostgreSQL RLS migration structure and tenant-policy inventory, including explicit identity-table exclusions and linked-supplier policy coverage.
- Runtime database-role bootstrap and column-grant policy inventory, including append-only event tables and no application DELETE privileges.
- Tenant context binding on the SQLAlchemy session and reapplication after commits (SQLite verifies session behavior; PostgreSQL GUC semantics require a real PostgreSQL check).
- Production configuration guard rejects demo seeding and public registration when `ENVIRONMENT=production`.

## Automated browser acceptance (RC11)

Five Playwright journeys are included under `e2e/`:

1. Factory administrator navigation, English/Japanese language switching and report CSV download.
2. Supplier portal navigation and role-boundary checks.
3. Factory PO creation → supplier confirmation/dispatch → warehouse partial receipt → QA failure → traceability quality hold.
4. Password recovery through the development-only action link, followed by sign-in with the new password.
5. Workspace invitation, one-time invitation acceptance, account activation and role-specific navigation.

Run the complete suite using the platform script:

```bash
# Linux / macOS
./scripts/e2e/run.sh

# Windows PowerShell
.\scripts\e2e\run.ps1
```

The scripts install `backend/requirements.txt` and `e2e/requirements.txt`, install frontend npm dependencies, install Playwright Chromium, and execute `python -m pytest -q e2e`. Equivalent manual commands are listed in `README.md`. The GitHub Actions `browser-e2e` job performs these steps on an Ubuntu runner and installs Chromium system dependencies.

The test fixture starts a fresh temporary SQLite database, FastAPI/Uvicorn and Vite. It uses fictional demo tenants and enables development-only reset/invitation action links. It removes its temporary database and logs after the run by default; set `FACTORYLINK_KEEP_E2E_LOGS=1` to retain the temporary directory. Playwright-managed Chromium is preferred; an installed system Chromium/Chrome is used as a fallback. Set `CHROMIUM_EXECUTABLE_PATH` to override browser selection.

**Scope limitation:** these UI journeys test browser-to-API behavior against SQLite. They do not prove PostgreSQL RLS/ACL, Docker runtime, concurrency semantics, real SMTP delivery, or production deployment. Those still require the real PostgreSQL and Docker acceptance steps below.

**RC11 execution status in this build environment:** the five tests were collected successfully and the Python suite compiled, but the browser journeys were not executed because `frontend/node_modules` could not be installed when npm registry DNS resolution failed (`EAI_AGAIN`). A standalone system-Chromium launch smoke passed; that is not the same as passing the FactoryLink browser journeys.

## Manual end-to-end acceptance

1. Log in as `admin@factorylink.jp` and verify dashboard, organisation, reports and audit views.
2. Change language to Japanese, refresh, and confirm preference persists. Switch back to English.
3. Log in as warehouse manager, create a new receipt and verify the lot traceability page shows the receipt movement.
4. Create a production order requiring some of that material. Move it `PLANNED → READY → IN_PROGRESS`, update completed/rejected output quantities and complete it. Verify stock consumption and ledger changes.
5. Attempt to reserve more material than available; the API should reject the transition without partial reservation.
6. Record a failed inspection linked to a batch, include corrective action, then verify the lot is on hold and excluded from normal reservations.
7. Log in as supplier user and confirm a shared PO, advance delivery status, and upload a document attached to the PO. Register a separate supplier workspace and verify its `SUPPLIER_ADMIN` can invite a `SUPPLIER_USER` colleague but cannot access manufacturer inventory.
8. Log in as the separate Tokyo tenant and verify it cannot see Sakura records.
9. Download CSV and XLSX reports. Check Japanese text and JPY formatting in the UI.
10. Verify the worker and scheduler create due-maintenance notifications once, not repeatedly.

## Historical build evidence (RC7)

The RC7 source executed the backend suite: **34 passed** on isolated SQLite. `python -m compileall -q app migrations tests` passed. Fresh Alembic migration through `0004_postgresql_tenant_rls` passed on SQLite (the PostgreSQL RLS operations are intentionally skipped by that dialect), and the idempotent seed script completed twice without duplicate records. A real Uvicorn process returned healthy status; factory login/dashboard and supplier login/linked-purchase-order listing succeeded against the seeded SQLite evaluation database. Docker Compose YAML parsed successfully with eight services, the database bootstrap/migration/runtime-role dependency structure was inspected, and `bash -n scripts/start.sh` passed. The frontend syntax check from the preceding release remains syntax-only; no dependency-backed type check or Vite production build has been executed for RC7.

Not executed in this environment: Docker image builds or container runtime, PostgreSQL 17 migrations/RLS policies/role grants, Redis/Celery containers, Vite production build, browser-level Playwright acceptance, PostgreSQL concurrency tests, or production deployment. `docker`, `psql`, and PostgreSQL server binaries are unavailable here. Do not interpret SQLite/API checks as evidence that PostgreSQL RLS or database-role permissions have been runtime-verified.


## Current build evidence (RC9)

The current RC9 source executed `python -m pytest -q`: **48 passed** on isolated SQLite. `python -m compileall -q app migrations tests` passed. A clean SQLite Alembic upgrade reached `0005_account_lifecycle`; the seed script ran twice and remained idempotent (3 organisations, 8 users, 1 supplier relationship, 2 purchase orders, 3 batches and 3 inventory movements). A live Uvicorn process returned health 200, authenticated the factory administrator, loaded the dashboard, authenticated the demo supplier and returned its two linked purchase orders. Frontend TS/TSX source transpilation reported zero syntax diagnostics; Nginx syntax validation, the eight-service Compose YAML structure, shell syntax and ZIP integrity checks passed.

Not executed: Docker image builds/container runtime, PostgreSQL 17 migration/RLS/runtime-role acceptance, Vite dependency-backed build/type check, Playwright/browser acceptance, PostgreSQL concurrency, real SMTP delivery or production deployment. These are explicitly outstanding before production.

## RC5 verification record (2026-11-03)

Executed in the available build environment:

- `python -m pytest -q`: **29 passed** (isolated SQLite API tests), including refresh-token family replay revocation, independent session preservation, production registration/seed guards, rejection of pre-dispatch receiving, supplier redispatch after a partial receipt, spreadsheet formula-injection protection, and controlled QA hold release.
- `python -m compileall -q app migrations tests`: passed.
- TypeScript/TSX syntax transpilation: 3 source files transpiled, 0 syntax diagnostics. This is syntax validation, not a dependency-backed `tsc -b` type check.
- Fresh Alembic upgrade to `head` (`0003_refresh_token_families`): passed against SQLite.
- Upgrade of a populated RC3 SQLite database to RC4: passed; existing records preserved and the new named FK/index present.
- Upgrade of an RC4 SQLite database to RC5 with a simulated legacy refresh-token chain: passed; old rotations were grouped into one family and independent legacy sessions were assigned distinct families.
- Nginx configuration syntax check: passed.

Not executed in this environment: Docker image builds, actual PostgreSQL/Redis/Celery containers, Vite production bundle, browser-level Playwright tests, concurrency tests against PostgreSQL, and a production deployment. An npm dependency installation attempt timed out, so this release does not claim a dependency-backed TypeScript type check or Vite build. Run these before using the system with real factory data.


## PostgreSQL RLS validation status

The `0004_postgresql_tenant_rls` migration is intentionally a no-op on SQLite and creates `ENABLE/FORCE ROW LEVEL SECURITY` policies on PostgreSQL. SQLite test success does not verify PostgreSQL policy semantics. Before production, run the dedicated PostgreSQL policy test plan in a real PostgreSQL 17 instance: test cross-tenant `SELECT`, `INSERT`, `UPDATE`, and `DELETE` denials for each tenant table; test linked supplier read/update behavior; test supplier document upload/download; test relationship notifications in both directions; test transaction context reapplication after commits; and test Celery reminders for multiple tenants.


## Runtime role acceptance checks

Against PostgreSQL, confirm the runtime role is `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, has no `BYPASSRLS`, does not own any application tables, cannot create/alter/drop objects, and cannot insert/update/delete `alembic_version`. Confirm the migration owner can still upgrade schema and that default DML grants apply to newly created application tables.


## PostgreSQL operator scripts

Two manual scripts are included under `scripts/db/` for a real PostgreSQL Compose run:

- `verify-runtime-role.sql` reports role flags and checks that the runtime login can read purchase orders and update only approved PO columns, but cannot update PO quantity, mutate audit history, delete records, or write Alembic's version table.
- `verify-rls.sql` uses the fictional demo tenants, switches to the runtime role, checks manufacturer isolation and linked-supplier visibility, tests permitted supplier-note updates and denied updates/deletes, then rolls the transaction back.

Run them with a PostgreSQL owner connection and set the psql variable `runtime_db_user` to the value in `.env`. These are real-PostgreSQL acceptance scripts; they have not been executed in this build environment.


## Account lifecycle tests

The backend suite covers password-reset account-enumeration behavior, one-time expiry/redemption semantics, refresh-session invalidation, invitation role validation, inactive-before-acceptance behavior, invitation replay rejection, and deprecation of administrator-assigned passwords. SMTP delivery is tested via the queue boundary; real provider acceptance, bounce handling and deliverability must be verified with the deployment's provider.


## RC10 current build evidence

- `python -m pytest -q`: **56 passed** from `backend/`.
- `python -m compileall -q app migrations tests`: passed.
- Fresh SQLite Alembic migration through `0005_account_lifecycle`: passed. Demo seed run twice with stable record counts.
- Live Uvicorn smoke: `/health` 200; factory demo login and `/api/v1/dashboard` 200 with 3 production orders; supplier demo login and `/api/v1/purchase-orders` 200 with 2 linked orders; OpenAPI exposed 36 paths.
- Limited local `tsc --noEmit` compatibility check of `App.tsx` and `i18n.ts` using temporary ambient declarations for unavailable dependencies (with `noImplicitAny` disabled): no diagnostics. TypeScript transpilation of the same 3 source files: no syntax diagnostics. This does not replace the real dependency-backed `npm run build`.
- Static frontend-to-backend route contract: every fixed API path in the React application is registered by FastAPI.
- Docker Compose YAML parsed and all 8 services/owner-vs-runtime database URLs were asserted. Docker daemon/runtime was unavailable.
- Runtime-role bootstrap and verification SQL were checked for broad revoke, regrant of explicit workflow columns, and Alembic write revocation. Run `verify-runtime-role.sql` and `verify-rls.sql` against PostgreSQL 17; no PostgreSQL service was available in this environment.
- `npm ping` failed with `EAI_AGAIN` resolving `registry.npmjs.org`; the full Vite production build and browser acceptance were therefore not run.


## RC11 browser acceptance suite

RC11 adds five Playwright journeys and a dedicated GitHub Actions `browser-e2e` job. Local execution is documented in `README.md`; use `scripts/e2e/run.sh` or `scripts/e2e/run.ps1` for a one-command setup and run. The current build environment verified Python compilation, test collection (5 tests) and a standalone Chromium launch, but did not execute the application journeys because npm package installation failed on registry DNS (`EAI_AGAIN`). Do not report the UI journeys as passed until they run successfully on a dependency-connected host or CI.

## PostgreSQL 17 / runtime-role acceptance

Run the real database and Redis acceptance path on a machine with PostgreSQL 17, `psql`, Redis, Python dependencies and a database owner credential:

```bash
bash scripts/db/postgres-acceptance.sh
```

The script tests fresh migration, repeatable demo seeding, re-running runtime-role bootstrap, role attributes and least-privilege column grants, RLS with no tenant context, factory tenant separation, linked supplier read visibility, denial of unlinked supplier records/orders and factory inventory, forbidden quantity update/delete/audit mutation, live API calls over the restricted role, post-commit tenant-context restoration, and a Redis/Celery maintenance reminder task. GitHub Actions runs the same script against PostgreSQL 17 and Redis services.


## RC12 — PostgreSQL receipt workflow acceptance

The PostgreSQL acceptance runner now goes beyond seeded reads. With PostgreSQL 17 and Redis available, `scripts/db/postgres-acceptance.sh` logs in as both factory and supplier runtime users, creates a new purchase order, submits it, has the supplier confirm and dispatch it, records a linked partial goods receipt as the factory runtime role, and confirms that the supplier can see the factory-confirmed received/remaining totals while remaining unable to read factory inventory batches. This live path exercises the `received_quantity` column grant and PostgreSQL trigger under tenant RLS. It then validates refresh rotation, user-language update, post-commit tenant context and a tenant-aware Celery reminder task. The CI job is configured; this PostgreSQL service run has not been executed in the current environment because no PostgreSQL server, Docker daemon or Redis service is available.


## RC13 verification evidence

- Backend: `PYTHONPATH=. python -m pytest -q` from `backend/`: **68 passed**.
- Fresh SQLite migration through `0006_supplier_receipt_progress` passed; demo seeding ran twice with stable counts (3 organisations, 8 users, 2 notifications, 3 batches and 2 inspections).
- Live Uvicorn smoke passed for administrator login, unread count, inventory CSV, quality XLSX, mark-all-read, zero unread after update, and supplier denial (403) for manufacturer reports.
- TypeScript transpilation reported no syntax diagnostics for `App.tsx`, `i18n.ts` and `main.tsx`. A local semantic pass with temporary ambient shims passed, but this is not the dependency-backed Vite build.
- E2E collection found **5 Playwright journeys**; actual browser journeys were not executed because frontend dependencies are unavailable. `npm install` timed out; `node_modules` is absent.
- `python -m compileall`, shell `bash -n`, Docker Compose YAML and GitHub Actions YAML parsing passed. Docker/PostgreSQL/Redis service startup and PostgreSQL RLS/ACL/trigger acceptance were not run here.


## RC14 — Production hardening tooling

Implemented request correlation IDs, JSON access logs that omit request payloads/headers/query values, internal process-local Prometheus-format counters, and separate liveness/readiness probes. Compose now uses `/health/ready` for backend health; Nginx proxies only health probes and does not expose `/metrics` publicly. Added PostgreSQL + uploads backup/restore scripts for Bash and PowerShell, SHA-256 manifests, retention configuration, restore confirmation and safe upload-volume content replacement. Added a localhost-restricted k6 read-path smoke profile.

Checks executed for RC14: backend tests **73 passed**; clean SQLite Alembic migration through `0006`; demo seed twice; live Uvicorn liveness 200, readiness returned 503 with `database=ok` and `redis=unavailable` because the local runner does not have the Redis Python client/server, metrics endpoint returned Prometheus text, and factory administrator login succeeded. Python compilation, Bash syntax and YAML parsing were also checked. Nginx configuration is validated through an HTTP-context wrapper because `limit_req_zone` belongs to the Nginx `http` context.

Not executed: Docker Compose runtime, PostgreSQL/Redis readiness success, actual PostgreSQL backup/restore, k6 load test, dependency-backed Vite build and complete Playwright browser journeys. Backup/restore scripts are source-reviewed and syntax-checked but require Docker Compose with running PostgreSQL and API services for functional execution.

## RC14 verification update

The RC14 run produced **73 passing backend tests**. A fresh SQLite database migrated through `0006_supplier_receipt_progress`; the demo seed ran twice with stable counts. Live Uvicorn checks returned liveness 200 with a request ID, Prometheus metrics text, factory admin login 200 and dashboard 200. Readiness returned 503 with database healthy and Redis unavailable because this environment has neither the Redis Python client nor a Redis server. Bash script syntax, Python compilation, k6 JavaScript syntax, Compose/CI YAML and Nginx syntax (with a local upstream substitution outside Compose) passed. A mocked Docker Compose CLI test exercised backup archive/checksum creation, restore command ordering, pre-restore copies and mounted-upload content replacement; it does not replace a real Docker/PostgreSQL restore drill. `npm run build` was attempted and failed because frontend packages are not installed (`vite/client` type definition missing). Docker/PostgreSQL/Redis, k6, Playwright app journeys, functional backup/restore, Vite build and PowerShell parsing remain unexecuted.

## One-command acceptance runner

From the repository root run `python scripts/acceptance/run.py --report /tmp/factorylink-acceptance.json`. It runs backend tests, compile checks, a clean Alembic migration, repeatable demo seeding and live HTTP checks against a temporary SQLite database. Docker, real Vite build, Playwright journeys and PostgreSQL/Redis/Celery checks are reported separately as skipped unless their prerequisites and opt-in flags are present. Use `--strict` in release environments to make any skipped optional gate fail the command.
