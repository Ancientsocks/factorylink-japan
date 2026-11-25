# FactoryLink Project Status

## Current code status — updated 2026-11-23

**Status: code-level release gates green; deployment gates not yet evidenced.**
This pass refreshed security-pinned dependencies and repaired the test suite so
the repository's own CI gates can pass. It made no Render, database, storage or
mail changes, and no deployment was performed.

- [x] Record edit/delete: suppliers, purchase orders, production orders,
  equipment, maintenance tasks, quality templates, users and documents now
  support editing and deletion with server-side state and integrity guards;
  **15 focused regression tests passed**.
- [x] Email verification: registration now sends a six-digit code, verifies it,
  then asks for the password; forgotten passwords use the same code flow, and
  the existing one-time link still works. Codes are hashed, expire after ten
  minutes, allow five attempts, are rate limited and single-use; **12 focused
  regression tests passed**, and the dev API plus browser sign-up and reset
  screens were exercised end to end. Real SMTP delivery remains unverified.
- [x] Email delivery: SMTP (multipart HTML + text) or the Resend HTTPS API, direct
  sending in development and a worker with direct fallback in production. The
  registration response now reports `email_sent: false` when no channel exists.
- [x] Google sign-in and sign-up: signed OAuth state, server-side code exchange,
  ID-token signature/issuer/audience/verified-email validation, single-use
  hand-off codes, passwordless Google accounts and a provider-aware button.
  **9 regression tests passed**; the hand-off and workspace form were driven in
  the browser. A real Google round-trip and real inbox delivery were not run.
- [x] Backend regression: **198 passed** on Python 3.12 with FastAPI 0.165.0 /
  Starlette 1.10.0; Python compilation passed.
- [x] Frontend: **8 vitest tests passed**; production `tsc -b && vite build`
  passed at Vite 7.3.8; `npm ci` installs from the committed lockfile.
- [x] Dependency audits: `pip-audit -r backend/requirements.txt` and
  `npm audit --audit-level=high`: **no known vulnerabilities**.
- [x] Local acceptance runner: **5 passed, 0 failed, 6 skipped** (compile,
  fresh Alembic migration through `0011_inventory_reconciliation`, repeatable
  seed, live API factory/supplier and manufacturing workflow).
- [x] Release-integrity tests now validate the staged two-step Render
  Blueprint instead of the deleted `render-database.yaml`.
- [ ] Docker Compose build/runtime, PostgreSQL 17 RLS/ACL, Redis/Celery,
  Playwright journeys, Render sync/deploy, private S3, SMTP delivery, external
  monitoring/alerting, backup/PITR drills and Japanese customer acceptance
  remain unverified for this revision; see `PRODUCTION_READINESS_AUDIT.md`.
- [ ] Render Stage 2 remains manual and intentional: copy
  `deploy/render-services.pending.yaml` into the root `render.yaml` after the
  database and restricted runtime credential are healthy, then sync the same
  Blueprint.

## Current local/staging status — updated 2026-11-05

## Current local/staging status — updated 2026-11-05

**Status: NOT PRODUCTION-READY.** The local Docker Linux engine was restored
after the earlier blocked attempt below. The latest application images were
built and the existing local database was upgraded from Alembic `0009` to
`0011_inventory_reconciliation`. The existing PostgreSQL and uploads volumes
were preserved. The backend, worker, scheduler and frontend were recreated
without removing volumes; backend readiness and frontend health returned HTTP
200, and the backend reported PostgreSQL, Redis and malware scanner checks as
healthy. Local application: `http://localhost:8080/`.

- [x] Latest full backend regression recorded before this packaging pass: **152
  passed**. This package adds a further Render/configuration regression test;
  the focused Render/release-integrity group in the packaging pass is **51
  passed**.
- [x] Isolated staging browser journeys: **3 passed**.
- [x] PostgreSQL end-to-end supplier procurement, receipt, inventory, quality,
  production, serial/shipment and genealogy workflow passed.
- [x] Redis rate-limit enforcement, client isolation and expiry passed.
- [x] Migration safety passed for empty install, populated predecessor upgrade,
  controlled failure/rollback, retry, data preservation, RLS and constraints.
- [x] Backup/restore drill passed into a separate verification database; table
  counts, Alembic version and uploaded-file hash matched.
- [x] Preliminary 5-user staging smoke test completed 25 workflow operations
  across 85 HTTP requests with no failed requests/operations and p95 latency
  around 145 ms. This is not a capacity or SLO certification.
- [ ] SMTP remains unconfigured. The Celery email test intentionally reached
  its configured retry/terminal failure path; real invitation and password-reset
  delivery has not been verified.
- [ ] Render, S3, external backups/PITR, external monitoring/alerts, Japan data
  processing approval and customer factory acceptance remain unverified.

The earlier Docker-engine outage record below is retained as history and is
superseded by the successful local/staging checks above.

## Historical status — before Docker engine recovery

**Status: NOT PRODUCTION-READY.** Docker Desktop's Linux-engine pipe is
unavailable, so current containers/images and the database revision could not
be inspected. No isolated staging stack was started. The reported backend
image `0008` / PostgreSQL `0009` mismatch is **unresolved**; current runtime
image and database revisions remain unverified. No existing database or
volume was intentionally modified.

### Staging attempt — 2026-11-05

- Read-only connectivity probe `docker compose ps --all` failed before Docker
  could return any resources:
  `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`;
  Windows reported that the named pipe could not be found.
- Consequently, container/image/project/volume inventory and the current
  development database and data-volume identities could not be established.
  Staging was not built or started, and no existing services or volumes were
  touched.
- All requested live staging gates remain unrun: latest image build/start,
  migration/head consistency, readiness, PostgreSQL acceptance and restricted
  role RLS, Redis throttling/expiry/isolation, concurrent reconciliation,
  migration failure/recovery, staging browser journeys, backup/restore, load
  measurements/database resource usage, and Celery retry/idempotency.
- **Exact external blocker:** Docker Desktop's Linux container engine is
  unavailable to this Windows session. Resume only after the engine is
  available; first perform the read-only container/image/project/volume
  inventory and positively identify development resources before creating
  staging with a new project name.

- [x] Corrected the inventory reconciliation resolution lock order to match
  the inventory scan path (batch before reconciliation row).
- [x] Added retry, late acknowledgement, worker-loss redelivery, and a
  PostgreSQL advisory lock for maintenance reminder jobs; added SQLite
  redelivery/idempotency coverage.
- [x] Added isolated PostgreSQL migration failure/recovery, restricted-role
  RLS, real Redis throttling, and concurrent inventory acceptance procedures.
- [x] Added a bounded staging load workload for manufacturing lifecycles,
  inventory receipts, and dashboard reads. HTTP starts are paced below the
  default API rate ceiling and the workload is capped at 2,000 operations.
- [x] Full backend regression: **152 passed**, 1 upstream
  Starlette/AnyIO deprecation warning (181.39 seconds).
- [ ] Staging image/migration verification, PostgreSQL/Redis acceptance,
  migration safety, backup/restore drill, and load execution: not run because
  Docker is unavailable.

| Task | Status |
|---|---|
| 1. Image/migration mismatch and isolated staging | **BLOCKED** |
| 2. Tenant security | **IMPLEMENTED BUT NOT VERIFIED** |
| 3. API rate limiting | **IMPLEMENTED BUT NOT VERIFIED** |
| 4. Inventory reconciliation | **IMPLEMENTED BUT NOT VERIFIED** |
| 5. Migration safety | **IMPLEMENTED BUT NOT VERIFIED** |
| 6. Backup and restore | **IMPLEMENTED BUT NOT VERIFIED** |
| 7. Monitoring and reliability | **IMPLEMENTED BUT NOT VERIFIED** |
| 8. Load testing | **IMPLEMENTED BUT NOT VERIFIED** |

The actual regression result and remaining evidence gates are recorded in
[TESTING.md](./TESTING.md). Do not deploy production images or treat the
implementation-only acceptance procedures as proof of live infrastructure.

## Production-readiness audit update — 2026-11-04

**Status: NOT PRODUCTION-READY.** See
[PRODUCTION_READINESS_AUDIT.md](./PRODUCTION_READINESS_AUDIT.md) for the
severity-ranked findings and release gate.

- [x] Updated the production-readiness audit with evidence-based P0/P1/P2
  findings, including the recorded `0008` backend image / `0009` database
  mismatch.
- [x] Updated deployment guidance with the guarded, interactive first-admin
  bootstrap procedure.
- [x] Updated the operations runbook to make external monitoring/alert
  ownership and delivery an explicit prerequisite.
- [x] Added a CI job to render production Compose configuration and build the
  production backend/frontend images using the placeholder example env file.
- [x] Preserved the separate production Compose topology and existing
  development configuration. No deployment was started.
- [x] Production Compose config render passed using `.env.production.example`.
- [x] Production backend and frontend images built successfully. The frontend
  image build ran `npm ci` and the TypeScript/Vite production build. Images were
  not started or promoted.
- [x] Backend suite: **140 passed**, 1 upstream deprecation warning. The first
  run caught a stale assertion expecting `npm install`; the test was updated
  to require `npm ci` and the lockfile, then the full suite passed.
- [x] Frontend unit suite: **8 passed**. Playwright browser journeys:
  **5 passed** on the isolated temporary SQLite test fixture.
- [x] Reviewed the production-critical application, migration, security,
  storage, infrastructure, deployment, Japan-localization, and testing paths.
  The scoped security review reported no exploitable vulnerability findings;
  it is not a penetration test.
- [ ] PostgreSQL migration/RLS and restricted-role tests, Redis/Celery,
  dependency/security scans, backup/restore drill, load test, hosted CI run,
  and staging deployment: **NOT RUN / NOT VERIFIED** in this pass.
- [ ] Production rollout remains blocked on the P0 image/schema consistency
  check and P1 tenant-isolation, staging, recovery, monitoring, capacity,
  Japanese customer/privacy, and external-provider evidence.

The prior record still reports the long-running backend image at migration
`0008` while PostgreSQL is at `0009`. A new production backend image was built,
but the existing container was not inspected, replaced, or restarted. No
database or Docker volume was deleted, recreated, restored over, or
intentionally modified during this pass. The filled local `.env` was not read.

## Latest acceptance update — 2026-11-04

**Status:** Finished-product inspection and traceability changes passed the local regression and live PostgreSQL acceptance checks below. Not production-certified or approved for real factory/customer data. A later scoped security review reported no exploitable vulnerability findings; it was not a penetration test.

- [x] Backend suite: **139 passed**, 1 upstream Starlette/AnyIO deprecation warning.
- [x] Frontend unit suite: **8 passed** across 2 files; production TypeScript/Vite build passed (1,580 modules).
- [x] Playwright journeys: **5 passed** after fixing an ambiguous product-field locator.
- [x] PostgreSQL workflow passed through the restricted runtime role: procurement → receipt → inventory → quality → reservation/consumption → finished batch and serial inspection → shipment and genealogy. Failed inspection/quarantine, CAPA transition guard, source-material hold blocking finished-product release, controlled release, insufficient stock, duplicate/excess receipts, invalid transitions and tenant denials were verified.
- [x] Additive migration `0009_finished_product_quality` applied to the existing PostgreSQL database.
- [x] PostgreSQL RLS transaction verified missing-context, factory and second-factory visibility for finished-product batches; all test inserts rolled back. Runtime-role grants passed.
- [ ] Redis/Celery were not rerun during this feature-specific regression; the previous 2026-11-04 acceptance run passed these checks.
- [ ] Production certification is not claimed. Backup/restore, load testing, customer/staging acceptance, and independent penetration testing remain outstanding.

**Database preservation:** Unique acceptance records remain in the existing PostgreSQL database; the additive migration preserved existing rows. No existing database or Docker volume was deleted or recreated.

**Runtime deployment note:** The existing backend and frontend images were not rebuilt or restarted. Current workspace backend source was mounted into temporary Compose containers for migration and live PostgreSQL acceptance; those temporary containers were removed. The long-running backend image still only knows migration `0008`, while PostgreSQL is at `0009`. Updating the deployed stack with this feature requires a later backend/migration image update.

**Finished-product quality:** Inspections can target a finished batch and optionally a serial. Failed inspection holds the batch, quarantines available serials and opens linked CAPA. Release requires a latest passing documented inspection and is blocked while any source material lot remains on hold. Finished-product inspection/CAPA history is exposed in forward and backward traceability; material-batch inspections remain supported.

Detailed commands and evidence are recorded in [TESTING.md](./TESTING.md).

## Latest update — RC24 — consolidated local release packaging

**Release:** Japan Local RC24 — 2026-11-03  
**Status:** Core-complete local evaluation candidate. Not production-certified, independently security-reviewed or approved for real factory data.

- [x] Preserved the RC22 core workflow work: inspection templates, CAPA evidence lifecycle, quality holds/releases, finished serial generation, lot/serial genealogy, QR/SVG and shipment records, and maintenance downtime classification.
- [x] Separated backend runtime dependencies from backend test dependencies.
- [x] Backend Docker build uses pinned runtime packages, binary wheels, bounded network retries/timeouts, and a configurable build-only Python package index.
- [x] Python package-index argument is not persisted in the final runtime image environment.
- [x] Docker startup scripts check Docker Engine availability and use plain build output to expose dependency errors.
- [x] Frontend Docker build suppresses unnecessary audit/funding network calls. Direct frontend package versions are pinned in `frontend/package.json`.
- [x] Historical release reports archived under `docs/releases/history/`; current RC24 evidence is under `docs/releases/`.
- [x] Added Windows setup instructions, user guide, release notes, and corrected workflow/RBAC documentation.
- [x] RC24 backend regression groups rerun: 66 passed across release-integrity, bootstrap, Render, mailer, malware scanner, object storage and the three focused core-workflow API cases. Prior RC22 grouped backend record: 130 passed (inherited, not a full RC24 rerun).
- [x] RC24 local acceptance runner: 5 passed, 0 failed, 6 skipped. Skips require Docker, npm/Vite/browser, and live PostgreSQL/Redis/Celery infrastructure.
- [ ] Docker build/runtime, dependency-backed frontend build/Playwright, PostgreSQL RLS/ACL/concurrency, Redis/Celery, real ClamAV/S3, backup/restore, load/security review and staging/customer acceptance remain unverified here.
- [ ] `frontend/package-lock.json` is not included because npm registry access was unavailable; direct package versions are pinned but frontend transitive dependencies are not lockfile-frozen.

See `docs/releases/RC24_BUILD_REPORT.md`, `docs/releases/RC24_ACCEPTANCE_RESULTS.json` and `FINAL_ACCEPTANCE_CHECKLIST.md`.

---

## Latest update — RC22 — core workflow completion

**Release:** Japan Local RC22 — 2026-11-03  
**Status:** Local core-complete candidate for user-run acceptance. Not production-certified or approved for real factory data.

### Original master-prompt core workflows delivered
- [x] Reusable tenant-scoped receiving/in-process/final quality templates with PASS/FAIL, numeric tolerance and text criteria.
- [x] Criterion-derived inspection result; a failed criterion overrides an entered PASS.
- [x] Failed-inspection quality hold and one-per-inspection CAPA record with containment, investigation, corrective/preventive action, verification and closure evidence gates.
- [x] Explicit audited batch release requiring the latest passing inspection and release reason.
- [x] Unique finished-product serial generation for each accepted unit when a production order completes; source material lots are recorded per serial.
- [x] Forward lot genealogy to PO/supplier/receipt, production orders, inspections, CAPA and finished serials; backward serial genealogy to production and material lots.
- [x] SVG QR generation for lots and serials; camera scanning via browser `BarcodeDetector` where supported, with manual search fallback.
- [x] Finished-serial shipment with customer/reference audit trail; serials from held source lots are quarantined and cannot ship.
- [x] Preventive/unplanned maintenance classification and downtime/availability analytics.
- [x] Quality, Traceability and Maintenance frontend workspaces connected to the new API routes; Japanese/English status labels updated.
- [x] API, database, README, changelog, acceptance checklist and build report updated.

### RC22 verification
- [x] Backend regression tests: **130 passed** across API, release-integrity, admin-bootstrap, Render, mailer, malware-scanner and object-storage test groups.
- [x] RC22 workflow regression tests: **3 passed**.
- [x] Fresh SQLite Alembic migration through `0007_quality_capa_serial_traceability` passed.
- [x] Repeatable demo seed passed; quality template and example CAPA were created.
- [x] Python compileall passed.
- [x] Frontend TSX syntax transpilation: zero syntax diagnostics for `App.tsx` and `i18n.ts`.

### Still requires local machine / real service acceptance
- [ ] Docker Compose build/start and full stack runtime.
- [ ] Dependency-backed Vite build/typecheck and Playwright browser journeys. npm installation timed out in this runner; no successful production frontend build is claimed.
- [ ] Real PostgreSQL 17 RLS/ACL/trigger/concurrency acceptance; SQLite does not validate PostgreSQL security semantics.
- [ ] Real Redis/Celery task and scheduler execution.
- [ ] Real ClamAV 1.5 warm-up, clean upload, EICAR test and scanner-outage upload rejection.
- [ ] Real S3/IAM integration, backup/restore drill, load test, independent security review and staging/customer acceptance.

**RC22 decision:** the previously identified core application workflow gaps are implemented in the local candidate. Run it using `scripts/start.ps1` (Windows) or `scripts/start.sh` (macOS/Linux), then send any local errors for repair. Do not use real factory/customer data or treat this candidate as production-approved until the outstanding environment and customer acceptance checks pass.

---

## Latest update — RC21 — ClamAV feature-line refresh and verified acceptance

**Release:** Japan Local RC21 — 2026-11-03  
**Status:** Evaluation candidate. Not production-ready, certified or approved for real factory data.

### RC21 changes
- [x] Updated official ClamAV service and scanner Dockerfile to the `1.5` feature line; scanner remains private-only with no published TCP port.
- [x] Updated version assertions, deployment guidance, README and final acceptance checklist.
- [x] Backend suite: **127 passed** (`python -m pytest -q` from `backend/`).
- [x] Acceptance runner: **5 passed, 0 failed, 6 skipped** when invoked with backend tests intentionally skipped; combining the separately executed backend pass gives **6 passed, 0 failed, 5 outstanding infrastructure gates**.
- [x] Fresh Alembic migration, two seed runs and live factory/supplier workflow passed.
- [x] Compose/Render/CI YAML parsed; nine Compose services; ClamAV has no host-published port; shell and k6 syntax checks passed.

### RC21 outstanding production gates
- [ ] Real Docker Compose + ClamAV 1.5 scanner runtime, signature warm-up and EICAR upload rejection / clean-upload test.
- [ ] PostgreSQL 17 RLS/ACL/trigger tests, Redis and Celery task execution.
- [ ] Dependency-backed Vite production build and all five Playwright browser journeys.
- [ ] Real private S3 integration and credential rotation.
- [ ] Real backup/restore drill, k6 load test, independent security review and staging/customer acceptance.

### RC21 environment limitations
- Docker/Podman, PostgreSQL and Redis binaries/services are unavailable in this runner.
- `frontend/node_modules` is absent and npm registry access has been unavailable, so Vite and browser journeys have not run.
- ClamAV protocol unit tests use a fake daemon; the real ClamAV container/signature database and EICAR route acceptance have not run.

## Latest update — RC20 — Fail-closed malware scanning for document uploads

**Release:** Japan Local RC20 — 2026-11-03  
**Status:** Local evaluation candidate; not production-ready or certified.

### RC20 changes
- [x] Added ClamAV INSTREAM scanning before local/S3 persistence.
- [x] Infected documents rejected with HTTP 422; scanner outage/invalid response fails closed with HTTP 503.
- [x] Production startup requires scanning enabled and a configured private scanner endpoint.
- [x] Readiness probe includes ClamAV PING when scanning is enabled.
- [x] Docker Compose includes a private ClamAV service and persistent signature database; scanner port is not published.
- [x] Added scanner service Dockerfile and Render/AWS deployment instructions.

### RC20 outstanding production gates
- [ ] Execute real Docker build/start for nine services; verify ClamAV database warmup, health and memory.
- [ ] Run controlled EICAR safe test, clean upload and scanner-outage test against real clamd; verify no persistence on reject/failure.
- [ ] Provision private S3 and verify upload/download/delete, IAM and object recovery.
- [ ] Execute PostgreSQL 17 RLS/ACL/trigger, Redis and Celery runtime acceptance.
- [ ] Pass dependency-backed Vite build and all five Playwright browser journeys.
- [ ] Execute real backup/restore, load tests, independent security review and staging/customer acceptance.

### RC20 local verification
- Backend suite: **127 passed** (`python -m pytest -q`).
- ClamAV INSTREAM clean/infected/error/timeout protocol tests use a local fake daemon; no real ClamAV database/container is claimed as executed.
- Docker Compose config/runtime and actual scanner image remain unverified because Docker is unavailable here.

---

## Latest update — RC19 — Private S3-compatible document storage

**Release:** Japan Local RC19 — 2026-11-03  
**Status:** Local evaluation candidate; not production-ready or certified.

### RC19 changes
- [x] S3-compatible object-storage adapter with local filesystem fallback for development.
- [x] Production startup rejects local storage and validates private S3 bucket/region/credential configuration.
- [x] Upload content validation and opaque key validation; S3 object SHA-256 metadata.
- [x] Authenticated attachment downloads are non-cacheable and use `nosniff` for local and S3 storage.
- [x] Render Blueprint accepts bucket and API-only secret values; AWS deployments can use workload IAM credentials.
- [x] Least-privilege S3 bucket/IAM instructions and separate object backup/restore requirements documented.

### RC19 outstanding production gates
- [ ] Provision a real private S3 bucket and verify IAM, encryption, versioning, upload/download/delete, rotation and recovery.
- [ ] Add and verify malware scanning before enabling external customer uploads.
- [ ] Execute Docker/PostgreSQL 17 RLS/ACL/trigger/Redis/Celery acceptance.
- [ ] Install frontend dependencies and pass a real Vite production build and five Playwright journeys.
- [ ] Execute real backup/restore, load tests, independent security review and staging deployment.

### RC19 local verification
- Backend tests: 105 expected after cache-control regression coverage; exact result recorded in `docs/releases/history/RC19_BUILD_REPORT.md`.
- Python compilation, clean migration, repeatable seed and live local API workflow are rerun in the acceptance report.
- S3 adapter and API route are tested with a fake S3 client; this is not a live AWS integration test.

---

## RC18 local verification

- Backend suite: **98 passed** (`python -m pytest -q` from `backend/`).
- Render runtime helper tests: role privilege rejection, same-database/different-credential URL validation, restricted grants and no role creation on the managed-credential path passed.
- One-time admin bootstrap tests: first manufacturer workspace/user/audit created on an empty database; a second bootstrap refused; weak passwords refused.
- Render Blueprint YAML parsed with PyYAML and static assertions verify separate owner/runtime credentials and all referenced services.
- Python compilation, fresh SQLite migration, repeated demo seed and the existing live API acceptance runner are rerun before packaging.
- Not executed here: Render Blueprint sync/account deployment, Docker runtime, PostgreSQL 17 RLS/ACL/trigger checks, Redis/Celery services, dependency-backed Vite build, Playwright browser journeys, real backup/restore and production load/security review.


## RC18 release verification

- Backend suite: **98 passed** (`python -m pytest -q` from `backend/`).
- Acceptance runner: **6 passed, 0 failed, 5 skipped**. Live API workflow, fresh migration, repeatable seed and Python compilation passed.
- Render Blueprint: YAML parsed and cross-service references statically checked; no Render CLI validation, sync or deployment was performed.
- Docker/PostgreSQL/Redis/Celery, npm/Vite production build and Playwright journeys remain outstanding in an environment with those services/dependencies.
