# FactoryLink — Final Local and Production Acceptance Checklist

**Current source version:** `1.0.0-rc.24`  
**Purpose:** verify the consolidated local application on the target Windows computer, then complete environment-specific production checks. Do not mark a skipped check as passed.

## 1. Core application features included in this release

- [x] Manufacturer and supplier workspaces, authentication, refresh-token rotation, invitations and role-based server-side checks.
- [x] Organisation-scoped supplier registry, purchase orders, supplier confirmation/dispatch, partial receipts and shared documents.
- [x] Inventory lots/batches, immutable stock movement ledger, FIFO reservations, production consumption and controlled adjustments.
- [x] Production orders, state transitions, progress, completion and reservation release on cancellation.
- [x] Reusable quality templates, server-derived inspection outcomes, defect records, CAPA lifecycle, batch hold and explicit evidence-gated release.
- [x] Finished-product serial creation for accepted production output, forward lot genealogy, backward serial genealogy, QR SVGs and shipment records.
- [x] Preventive/unplanned maintenance tasks and downtime analytics.
- [x] Tenant-scoped dashboards, notifications, audit history, CSV/XLSX reports and English/Japanese UI.
- [x] Docker Compose source for PostgreSQL, Redis, ClamAV, API, worker, scheduler and frontend.

These code-level features have backend regression coverage; the service-dependent and browser checks below are still required on the target computer.

## 2. Windows local startup

- [ ] Install Docker Desktop with WSL 2 and Linux containers enabled.
- [ ] Start Docker Desktop and verify both `docker version` Client and Server sections are shown.
- [ ] Allocate around 4 GiB RAM or more for ClamAV signature loading.
- [ ] Extract `FactoryLink-Japan-Complete-Release.zip` to a writable folder.
- [ ] Review `.env`; keep local/demo flags restricted to localhost.
- [ ] Run `.\scripts\start.ps1` from the project root.
- [ ] Verify `docker compose ps` shows PostgreSQL, Redis, ClamAV, API, worker, scheduler and frontend healthy/completed as expected.
- [ ] Open `http://localhost:8080`, `/docs`, `/openapi.json` and `/health/ready`.

## 3. Browser and workflow acceptance

- [ ] Sign in with each demo role and verify role-appropriate navigation and API denials.
- [ ] Switch English/Japanese and verify forms, dates, JPY formatting and Japanese data.
- [ ] Complete supplier PO submission → supplier confirmation/dispatch → partial/final goods receipt.
- [ ] Verify each receipt creates a lot and ledger movement and cumulative received quantity cannot exceed the PO.
- [ ] Run a passing quality template and a failing quality template; verify the failed lot is held and CAPA is opened.
- [ ] Complete the CAPA evidence lifecycle and verify that a later passing re-inspection plus release reason is required to clear the hold.
- [ ] Complete a material-backed serial-tracked production order; verify serial count equals accepted completed units and source lot genealogy is present.
- [ ] Search a lot forward and a serial backward; download both QR SVGs and test camera scanning where supported, then test manual search fallback.
- [ ] Record a finished-serial shipment and verify held-source serials cannot ship.
- [ ] Test preventive/unplanned maintenance records and downtime analytics.
- [ ] Verify dashboards, reports, notifications and audit events are based on persisted records.
- [ ] Run all five Playwright browser journeys.

## 4. Backend and infrastructure acceptance

- [x] RC24 backend regression groups rerun: 66 passed across three groups.
- [x] Prior RC22 grouped backend suite record: 130 passed; this is inherited evidence, not a full RC24 rerun.
- [x] RC24 packaging-environment local acceptance runner: 5 passed, 0 failed, 6 skipped (Docker, frontend/browser and real PostgreSQL/Redis/Celery gates require target infrastructure).
- [ ] From `backend/`, run `python -m pip install -r requirements-dev.txt`, `python -m pytest -q` and `python -m compileall -q app migrations tests`.
- [ ] Run `python scripts/acceptance/run.py --report acceptance-report.json`.
- [ ] Run the Vite dependency-backed frontend build: `cd frontend; npm install --no-audit --no-fund; npm run build`.
- [ ] Run Playwright: `python -m pip install -r backend/requirements.txt -r e2e/requirements.txt; python -m playwright install chromium; python -m pytest -q e2e`.
- [ ] Run PostgreSQL 17 RLS/ACL/trigger/concurrency acceptance using `bash scripts/db/postgres-acceptance.sh` in an environment with the documented variables and Redis.
- [ ] Verify Redis, Celery worker and scheduler execute their real jobs.
- [ ] Verify ClamAV 1.5 signature warm-up, clean upload, safe EICAR rejection in isolated staging, and fail-closed behavior when scanner is unavailable.
- [ ] If S3 is configured, verify real private bucket upload/download/delete, IAM scope, object hashes and credential rotation.

## 5. Production go-live gates

Before any public or real-factory deployment:

- [ ] Set `ENVIRONMENT=production`, strong unique secrets, `SEED_DEMO_DATA=false`, `ALLOW_PUBLIC_REGISTRATION=false` and `EXPOSE_AUTH_ACTION_LINKS=false`.
- [ ] Use PostgreSQL over TLS, a separate migration owner and a restricted non-owner runtime DB role.
- [ ] Use private Redis, private S3-compatible object storage, private malware scanner networking, HTTPS ingress and correct CORS origins.
- [ ] Configure real SMTP and verify reset/invitation delivery.
- [ ] Run encrypted database and document backup, restore and recovery drills.
- [ ] Run load/performance tests and independent security/privacy review; resolve critical/high findings.
- [ ] Validate Japanese terminology, business process and record-retention expectations with a Japanese manufacturing customer and qualified advisors.
- [ ] Obtain explicit factory-owner approval before importing real data or enabling production access.

**Release classification:** RC24 is a core-complete local evaluation candidate. This checklist is not a claim of certification, regulatory compliance or production approval.
