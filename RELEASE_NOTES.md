# FactoryLink — Release Notes

## Japan Local RC23 — 2026-11-03

**Purpose:** consolidated local evaluation release with core manufacturing workflows and packaging/build diagnostics improved.

### Included product capabilities

- Multi-tenant manufacturer and supplier workspaces, authentication, refresh-token rotation, role-aware navigation and server-side permission checks.
- Supplier registry, purchase orders, confirmation/dispatch, partial receipt and supplier-only document access.
- Materials, lots/batches, inventory movements, FIFO reservations, consumption and reason-coded adjustments.
- Production orders, progress, cancellation/reservation release and finished-product serialisation for accepted units.
- Reusable quality inspection templates, defect records, CAPA lifecycle, batch holds and explicit controlled release.
- Forward lot genealogy, backward serial genealogy, QR SVGs, camera scanning where browser support exists, and finished-product shipment records.
- Equipment registry, preventive/unplanned maintenance classification and downtime analytics.
- Real-data dashboards, notifications, audit history, CSV/XLSX exports and English/Japanese UI.
- Docker Compose services for PostgreSQL, Redis, ClamAV, API, worker, scheduler and Nginx frontend.

### RC23 packaging and build improvements

- Backend runtime requirements separated from pytest/HTTPX development requirements.
- Backend image installs pinned binary wheels, with bounded pip retries/timeouts and a configurable package index.
- Docker startup scripts check engine availability and use plain progress to retain package resolver output.
- S3 storage settings are passed through to the API container when configured.
- Historical RC evidence is archived under `docs/releases/history/`; current release evidence lives under `docs/releases/`.
- Added Windows setup, user guidance and local setup troubleshooting.

### Verification status

- RC24 backend regression groups rerun: **66 passed** across release-integrity/admin-bootstrap/Render-deploy (44), mailer/malware-scanner/object-storage (19), and three focused core-workflow API cases (3).
- Prior RC22 full backend regression record: **130 passed** across test groups; this is inherited evidence, not a full RC23 re-run.
- Reproducible local acceptance runner executed in this packaging environment: **5 passed, 0 failed, 6 skipped**. Backend test execution was intentionally disabled in that invocation; fresh SQLite migration, compile, idempotent demo seed and live Uvicorn manufacturing workflow passed.
- Compose/Render/CI YAML parsing, shell syntax checks and k6 JavaScript syntax check passed according to RC23 build records.

### Not verified in this environment

- Docker image build and complete Compose runtime.
- npm dependency installation, Vite typecheck/production build and Playwright browser journeys.
- A frontend `package-lock.json`; npm registry access was unavailable, so direct dependency versions are pinned but transitive npm dependencies are not frozen by a lockfile.
- PostgreSQL 17 RLS/ACL/triggers/concurrency, Redis/Celery, real ClamAV signature load/EICAR behavior and real S3/IAM.
- Backup/restore, load testing, independent penetration/security review, staging deployment and factory/customer acceptance.

### Release classification

RC23 is a **core-complete local evaluation candidate**, not a certified or production-approved application. Use fictional demo data until all applicable checks in `FINAL_ACCEPTANCE_CHECKLIST.md` are completed and a factory owner approves use.
