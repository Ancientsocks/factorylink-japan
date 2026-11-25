# Changelog

## Unreleased — production-readiness hardening — 2026-11-23

- Fixed PostgreSQL privilege gaps that would have broken the new record editing and deleting in production. Migrations `0011`–`0013` granted the runtime role privileges without checking that it exists, which aborted `alembic upgrade head` on a managed database where the role is created separately (Render, external PostgreSQL); those grants are now guarded like `0004`–`0009`. New migration `0014_runtime_edit_delete_grants` grants exactly the columns the `PATCH` endpoints write and `DELETE` on the six record tables staff may clear — `suppliers`, `purchase_orders`, `production_orders`, `equipment`, `maintenance_tasks`, `attachments` — while audit, ledger and inspection history stay append-only. `scripts/db/create-runtime-role.sql`, the Render grant path and `scripts/db/verify-runtime-role.sql` follow the same reviewed matrix.
- Upgraded vulnerable pinned dependencies: FastAPI 0.165.0 (Starlette 1.10.0), PyJWT 2.15.1, python-multipart 0.0.34, pydantic-settings 2.14.2; Vite 7.3.8 and Vitest 5.1.1 on the frontend. `pip-audit` and `npm audit --audit-level=high` now report no known vulnerabilities.
- Fixed the frontend authentication-error test to submit credentials so it exercises the server-provided error instead of relying on skipped constraint validation.
- Updated the Render release-integrity tests to validate the staged two-step Blueprint: the database-only root `render.yaml` plus the reviewed application configuration in `deploy/render-services.pending.yaml`.
- Removed committed `.bak` source and Dockerfile copies and ignored generated `*.tsbuildinfo` files.
- Added edit and delete to the interface for suppliers, purchase orders, production orders, equipment, maintenance tasks, quality templates, users and shared documents, with confirmation dialogs and role-aware row actions. New `PATCH`/`DELETE` endpoints enforce mutable-state rules, tenant scoping and referential-integrity guards, and every change is written to the audit log. Accounts are deactivated and quality templates retired instead of erasing attribution.
- Fixed a page-switch crash that blanked the application: a module could render with the previous module's data shape. Pages now only receive their own payload, and an error boundary keeps a failed screen visible instead of unmounting the app.
- Removed the `backdrop-filter` blur from modal and help-guide overlays, which could paint as a solid black layer on some Windows GPU configurations.
- Added email ownership verification to account creation and password recovery. New workspaces now collect company details, email a six-digit code, verify it, and only then ask for the sign-in password; forgotten passwords use the same code flow (email → code → new password) while the existing one-time link still works. Codes are stored as hashes with a ten-minute expiry, five attempts, a sixty-second resend cooldown and a single-use fifteen-minute verification ticket; registration requires `email_verification_token`, reset confirmation accepts either the link ticket or the code ticket, and unknown reset addresses return the same response so accounts cannot be enumerated. Raw codes and tickets are only returned in development without SMTP.
- Made verification email actually deliverable: SMTP now sends multipart HTML + text with proper headers, and `RESEND_API_KEY`/`RESEND_FROM` add an HTTPS delivery channel that needs no SMTP port. Development sends immediately instead of depending on a Celery worker, production queues and falls back to a direct send if the broker is down, delivery failures are logged, and the registration response reports `email_sent: false` with an actionable message instead of pretending a code was emailed. `cryptography` was added for RS256 identity-token verification.
- Added Google sign-in and sign-up. The browser is sent to Google's authorization endpoint with a signed state, the API exchanges the code and validates the ID token (signature, issuer, audience, verified email), and hands the SPA a single-use five-minute code to trade for a session. New Google users complete the workspace form without a password; existing accounts sign in directly; inactive accounts are refused. Google-only accounts can later set a password through the code-based reset. Endpoints are rate limited and the UI hides the button when the provider is not configured.
- Fixed fresh-database migrations: `0001_initial` creates the current model metadata, so `0012` and `0013` failed with "table already exists" on a brand-new database. Both migrations now inspect the schema and skip existing tables, columns and indexes, so new installs and existing databases both upgrade cleanly.
- Added explicit back buttons to the email and code screens and a 60-second resend control that mirrors the server cooldown.
- Verification: backend 206 passed (including 16 new Google and email-delivery tests); frontend 8 passed and a production Vite build passed; the register-with-code, reset-with-code, Google sign-in hand-off and Google workspace sign-up flows were exercised in the browser against the dev stack. A real Google OAuth round-trip and real inbox delivery were not exercised because no Google client ID or email credentials exist in this environment.
- PostgreSQL was verified directly: a clean PostgreSQL 17 database migrated `0001`→`0014`, the least-privilege runtime role (`factorylink_app`) passed `scripts/db/verify-runtime-role.sql`, and authenticated create/edit/delete calls succeeded through that role against seeded data — proving the privilege matrix now matches the UI rather than only SQLite.
- Still not production-approved: Playwright browser journeys, Render deployment, private S3, real SMTP/Resend delivery to a company inbox, a real Google OAuth consent round-trip, monitoring/alerting and backup/PITR drills were not run in this pass.

## 1.0.0-rc.24 — Consolidated local release packaging — 2026-11-03

- Kept the RC22 core manufacturing workflow additions as the application baseline.
- Separated backend runtime dependencies from backend development/test dependencies.
- Hardened backend Docker dependency installation with binary wheels, bounded retries/timeouts and a configurable build-only package index; the index URL is not persisted in the runtime image environment.
- Improved Docker startup diagnostics and frontend install build behaviour.
- Archived historical release reports, added Windows setup and user guidance, and corrected obsolete CAPA/RLS workflow documentation.
- Added a single consolidated release acceptance checklist and RC24 release report.
- Validation: RC24 local acceptance runner 5 passed/0 failed/6 skipped; 66 backend regression cases passed across three groups. Docker runtime, browser build/E2E, live PostgreSQL/Redis/Celery and production service checks remain not run.

# Changelog — FactoryLink

## RC23 — 2026-11-03

- Hardened the backend runtime image: runtime-only dependencies, binary-wheel installation, retry/timeout settings and configurable package index.
- Added Docker Engine preflight and plain Compose build output for easier local diagnosis.
- Wired S3 storage configuration through Docker Compose.
- Reorganized historical release evidence under `docs/releases/history/` and added the RC23 report and acceptance record to the release history and added the troubleshooting guide.


## 1.0.0-rc.22 — Core manufacturing workflow completion — 2026-11-03

- Added tenant-scoped reusable quality inspection templates with PASS/FAIL, numeric tolerance and text criteria; API-derived failures override a submitted PASS.
- Added a controlled CAPA case per failed inspection, with evidence-gated containment, investigation, corrective/preventive action, verification and closure.
- Added production serial tracking and one finished-product serial per accepted completed unit, with consumed material-lot genealogy.
- Extended lot and serial traceability through supplier, purchase order, receipt, production, inspection, CAPA and finished-product shipment.
- Added SVG QR generation for lot/serial identifiers, browser camera scanning where `BarcodeDetector` is available, and manual search fallback.
- Added customer/shipment references for finished serials and fail-safe quarantine when a source lot is on quality hold.
- Added preventive/unplanned maintenance classification and downtime/availability analytics.
- Connected Quality, Traceability and Maintenance screens to the new APIs and updated Japanese/English labels.
- Verification: 130 backend regression tests passed across the API and supporting test groups; three focused RC22 workflow tests passed; fresh SQLite migration to `0007_quality_capa_serial_traceability`, demo seed, Python compilation and frontend syntax transpilation passed.
- Not executed here: Docker runtime, dependency-backed Vite build/Playwright, real PostgreSQL RLS/ACL, real Redis/Celery, ClamAV runtime, S3, backup/restore, load, security review or staging/customer acceptance. See `docs/releases/history/RC22_BUILD_REPORT.md`.

## 1.0.0-rc.21 — ClamAV feature-line refresh and verified local acceptance — 2026-11-03

- Updated the official ClamAV container from the 1.4 to the 1.5 feature line. The official image guidance recommends feature-version tags so patch updates within the selected feature release can be consumed without floating to a new feature line.
- Updated Compose, scanner Dockerfile, deployment documentation and release-integrity assertions to use `clamav/clamav:1.5`.
- Re-ran the backend regression suite: **127 passed**.
- Re-ran the reproducible acceptance runner: Python compile, clean Alembic migration, repeatable seed, and live factory/supplier manufacturing workflow passed (**5 passed, 0 failed**); Docker, frontend build, browser and PostgreSQL/Redis/Celery checks were skipped because the required tools/services are unavailable.
- Parsed Compose/Render/CI YAML; verified nine Compose services and confirmed ClamAV has no host-published port. Bash and k6 JavaScript syntax checks passed.
- This is still an evaluation candidate. Real ClamAV daemon/EICAR upload, Docker, PostgreSQL/RLS, Redis/Celery, Vite, browser, S3, restore, load, security-review and staging gates remain open.

## 1.0.0-rc.20 — Fail-closed malware scanning for document uploads — 2026-11-03

- Added a ClamAV `clamd` INSTREAM client that streams bounded document bytes in chunks and accepts only a clean `stream: OK` response.
- Document uploads are scanned after size/type/signature validation and before any local or S3 persistence. Infected files return HTTP 422; scanner timeouts, invalid replies or service outages return HTTP 503 and leave no object or attachment row.
- Production startup now requires malware scanning enabled and a configured private scanner host/port/timeout.
- Readiness checks now include ClamAV PING when scanning is enabled.
- Added an internal-only ClamAV service to Docker Compose with persistent signature database and a health check; port 3310 is never published to the host.
- Added a separate scanner Dockerfile and Render/AWS deployment requirements for private networking and sufficient memory.
- Added regression coverage for clean, infected, malformed, unavailable, fail-closed API and production configuration cases.
- The official ClamAV protocol uses framed TCP commands and INSTREAM; its TCP interface is unencrypted and unauthenticated, so the service is confined to the application private network (no public port).




## 1.0.0-rc.17 — Live manufacturing workflow acceptance — 2026-11-03

- Extended the one-command acceptance runner to execute the full supplier-to-factory operational journey against a live Uvicorn server and a fresh migrated/seeded SQLite database.
- The live flow creates/submits a purchase order, has the supplier confirm and dispatch it, records a linked factory goods receipt, verifies supplier-visible receipt totals, creates and completes a material-backed production order, records a failed quality inspection, verifies the batch is held, and checks traceability event history.
- Added a release-integrity regression test requiring the live acceptance runner to retain all critical workflow stages.
- Added an opt-in isolated Docker Compose runtime smoke with unique project/volume names, health/UI/API checks and automatic teardown; wired it into a dedicated Docker-enabled CI job.
- Latest verified run: 88 backend tests passed; acceptance runner 6 passed, 0 failed, 5 skipped. Skips are Docker Compose config/runtime, npm/Vite build, Playwright browser execution and PostgreSQL/Redis/Celery runtime because the required tools/dependencies are not available on this host.

# Changelog

## 1.0.0-rc.19 — Durable private object storage — 2026-11-03

- Added a storage adapter with atomic local development storage and an S3-compatible production backend; S3 SDK imports are lazy so local development does not require cloud credentials.
- Production startup now rejects local storage and requires a private S3 bucket, region, paired explicit credentials (or the cloud default credential chain), and HTTPS for custom S3 endpoints.
- Added bounded key validation, SHA-256 object metadata, private `PutObject`/`GetObject`/`DeleteObject` calls without public ACLs, and safe object-not-found/error handling.
- Added a Boto3 dependency pin and Render secret placeholders for the private document bucket.
- Added local/S3 adapter tests, API upload/download tests and production-storage startup guard tests; downloads are explicitly `private, no-store` and `nosniff` for both storage providers.
- Documented least-privilege S3/IAM setup, bucket encryption/versioning, credential management and separate object-storage backup/restore requirements.
- Local verification: 105 backend tests pass after document-download cache controls; clean migration/seed and live local API acceptance are rerun before packaging. Real AWS S3, Docker/PostgreSQL/Redis, Vite build and Playwright journeys are not claimed as executed.


## 1.0.0-rc.18 — Production onboarding and Render credential hardening — 2026-11-03

- Added a one-time, operator-only first factory administrator command; no public bootstrap endpoint or default password exists.
- Added atomic creation of the first manufacturer workspace, `ORG_ADMIN` user and audit event; bootstrap refuses to run after any tenant/user exists.
- Added a Render-managed runtime credential path that validates the target role and inherited memberships without requiring CREATE ROLE/ALTER ROLE on the Render database owner.
- Kept Compose/CI role creation on the self-managed PostgreSQL path while making Render migrations use the owner credential and long-running services use the restricted runtime URL.
- Added an initial Render Blueprint for private API, public Docker/Nginx frontend, PostgreSQL, Redis-compatible Key Value, worker and scheduler services.
- Documented the two-credential provisioning order and one-time administrator bootstrap.
- Added regression tests for role validation, reviewed GRANT statements, runtime URL pairing and first-admin bootstrap.
- Local verification: 96 backend tests pass. Render Blueprint was YAML-parsed and statically inspected; no live Render sync, Docker/PostgreSQL runtime, npm/Vite build or Playwright browser run is claimed.

## 1.0.0-rc.16 — Reproducible acceptance runner

- Added a single Python acceptance runner for backend tests, compilation, clean migrations, idempotent seed, and live API role/report smoke checks.
- The runner reports missing Docker, frontend dependencies, Playwright browser, PostgreSQL, Redis and Celery prerequisites as `SKIP` rather than false passes.
- Added a dedicated CI job and downloadable JSON acceptance report.
- Fixed case-insensitive HTTP response-header handling and readiness polling in the runner.
- Redacted demo credentials from saved subprocess logs and acceptance JSON reports.
- Added local Windows/Linux usage instructions and strict-mode behavior.


### Enterprise notifications and operational reporting
- Added an organisation-scoped unread-notification count endpoint and bulk mark-all-as-read operation.
- Replaced the placeholder notification dot with an unread count in desktop/mobile navigation and the header bell.
- Added a notification preview with direct mark-read actions and a full notification screen with All, Unread and Needs Attention filters.
- Added Inventory CSV/XLSX exports with lot-level on-hand, reserved, available, unit-cost and JPY stock-value columns.
- Added Quality CSV/XLSX exports with inspection outcome, lot, sample size, defect count, defect rate and corrective-action fields.
- Kept all new exports organisation-scoped and explicitly denied supplier accounts access to manufacturer inventory/quality exports.
- Applied spreadsheet formula-injection protection to exported text and added Excel string-cell typing, frozen headers and filters.
- Expanded backend coverage to **68 passing tests**, including tenant-scoped notification bulk-read, report permissions, formula-safe exports and quality defect-rate accuracy.

### RC13 verification record
- Fresh SQLite Alembic migration through `0006_supplier_receipt_progress`: passed.
- Demo seed executed twice: passed with stable counts (3 organisations, 8 users, 2 notifications, 3 batches and 2 inspections).
- Live Uvicorn smoke passed for admin login, unread count, inventory CSV, quality XLSX, mark-all-read, refreshed count and supplier export denial.
- Frontend TypeScript/TSX syntax transpilation and limited local `tsc --noEmit` compatibility check with temporary declarations (with `noImplicitAny` disabled): passed. The real dependency-backed Vite build was not run because `npm install` timed out and `node_modules` is absent.
- Playwright E2E suite collection: 5 tests collected; browser journeys not executed.
- Docker Compose and GitHub Actions YAML parse, shell syntax and Python compilation: passed. Docker/PostgreSQL/Redis runtime and deployment remain unverified in this environment.

## RC11 — Browser acceptance foundation

- Added five Playwright browser journeys covering bilingual factory navigation and CSV export, supplier portal permission boundaries, linked PO dispatch/partial receipt/quality hold/traceability, password recovery, and invitation acceptance.
- Added isolated E2E fixtures that start FastAPI/Uvicorn and Vite against a fresh temporary SQLite database with fictional demo tenants.
- Added Linux and Windows one-command E2E runners; both now install backend and E2E Python dependencies before frontend packages and Chromium.
- Added a dedicated GitHub Actions browser acceptance job with Node 22, Python 3.12 and Playwright Chromium.
- Verification in this environment: backend suite **57 passed**; Python compilation and browser test collection (**5 tests**) passed; Compose YAML/CI workflow YAML parsed; standalone Chromium launch smoke passed.
- Not verified here: the five actual FactoryLink browser journeys, dependency-backed Vite build, Docker/PostgreSQL runtime, PostgreSQL RLS/ACL acceptance, SMTP provider delivery or deployment. npm registry DNS failed (`EAI_AGAIN`), so frontend dependencies were unavailable; Docker is not installed.

## RC7 — 2026-11-03

### Tenant isolation and deployment hardening
- Added PostgreSQL `ENABLE/FORCE ROW LEVEL SECURITY` policies to organisation-owned operational tables and explicit linked-supplier policies.
- Bound tenant context from the verified access token and re-applied transaction-local context after commits.
- Scoped the Celery maintenance reminder task tenant-by-tenant for RLS compatibility.
- Added a database bootstrap service for a dedicated non-owner, non-superuser runtime role.
- Split Alembic/optional demo seed into a one-shot owner-credential migration service; API and Celery use the restricted runtime account.
- Revoked runtime writes to Alembic bookkeeping, denied application deletes, and restricted UPDATE to workflow-specific columns.
- Added real-PostgreSQL operator scripts for tenant isolation and runtime-role acceptance; these scripts still require execution on PostgreSQL.
- RC7 verification: **34 backend tests passed** on SQLite; fresh migration/seed, Uvicorn API smoke, Compose YAML parsing and shell syntax checks passed. PostgreSQL/Docker runtime and frontend production build remain unverified in this environment.

## RC6 — PostgreSQL tenant isolation

- Added PostgreSQL `ENABLE/FORCE ROW LEVEL SECURITY` policies for operational tenant tables.
- Added transaction-local tenant binding from the verified JWT organisation claim and reapplication after commits.
- Added explicit linked-supplier policies for supplier records, purchase orders, notification fan-out, and shared purchase-order attachments.
- Updated the Celery maintenance reminder task to scope each tenant independently.
- Documented RLS coverage, non-covered identity tables, and the required real-PostgreSQL acceptance tests.

## RC5 — 2026-11-03

### Security
- Added refresh-token family identifiers per login session.
- Detects replay of rotated refresh tokens and revokes active descendants in the affected family.
- Independent sessions for the same user remain valid.
- Added regression tests for token replay and session isolation.
- Made demo seeding configurable through `.env` instead of hard-coding it in Compose.
- Added configurable public workspace registration; production startup refuses unsafe settings if demo seeding or public registration is still enabled.
- Added Alembic migration `0003_refresh_token_families`, including migration of historical rotation chains.

### Verification
- Backend test suite: 29 passed on isolated SQLite.
- Fresh Alembic migration and populated RC4-to-RC5 SQLite migration passed.
- Legacy token-family migration verified with a simulated ancestor/descendant chain and separate login session.
- Live Uvicorn smoke verified the token-family replay behavior: login/rotation 200, replay and descendant reuse 401, independent session refresh 200.
- Docker/PostgreSQL runtime, dependency-backed frontend build, and browser E2E remain unverified in this environment.

## 1.0.0-rc4 — 2026-11-03

- Linked material batches to their originating purchase orders; a goods receipt is now traceable from supplier commitment through lot and inventory movements.
- Added partial-receipt accounting from the immutable receipt ledger, remaining-quantity reporting, receipt overrun prevention, and automatic `PARTIALLY_DELIVERED` / `DELIVERED` transitions.
- Restricted supplier purchase-order transitions to confirmation and dispatch; suppliers cannot mark goods delivered before the factory records receipt.
- Added an SQLite-safe Alembic upgrade for existing RC3 databases while retaining compatibility with fresh databases whose initial metadata already includes the new field.
- Added cancellation of active production orders with safe reservation release, including stock on quality hold.
- Strengthened document uploads with content-signature checks, safe display names, extension allowlisting, size limits and cleanup on failed database writes.
- Added Nginx login and registration request throttling and improved refresh-token expiry handling in the browser client.
- Added per-context Docker ignore files and delivery-progress display in the purchase-order UI.
- Corrected fresh demo seed data so partial receipts reconcile exactly to linked purchase orders.
- Required supplier dispatch before linked physical receipt and added supplier redispatch for remaining quantities after a partial receipt.
- Escaped formula-like text in CSV/XLSX production exports to prevent spreadsheet formula injection.
- Added controlled quality-hold release: only QA/admin can release a lot after its latest linked inspection passes with documented notes and an auditable release reason.
- Expanded the cross-module supplier → purchase order → goods receipt → production → quality → traceability test; backend suite now has 25 passing tests.
- Verified upgrade from a populated RC3 SQLite database and fresh RC4 migration in the local test environment. Docker runtime and Vite production build remain unverified here.

## 1.0.0-rc3 — 2026-11-03

- Added production output editing for completed and rejected quantities in the production screen.
- Exposed valid production transitions, including pause, resume, complete and cancel actions.
- Added equipment registration directly from the maintenance screen.
- Added reason-coded positive/negative inventory adjustments with ledger, audit and traceability events.
- Prevented production completion from consuming a batch placed on quality hold after its reservation.
- Fixed Nginx forwarding for `/docs`, `/redoc` and `/openapi.json`.
- Updated Windows/Linux startup scripts to wait for service health and show logs on failure.
- Expanded backend API tests to 16 passing tests.

## 1.0.0-rc2 — 2026-11-03

- Added first-time manufacturer and supplier workspace registration.
- Added supplier workspace linking by company code and cross-factory supplier purchase-order visibility.
- Improved role-aware UI navigation and hid actions that the signed-in role cannot perform.
- Made the document language attribute follow the selected Japanese/English locale.
- Improved small-screen registration form scrolling.
- Expanded backend verification to 13 API tests and an Alembic migration smoke test.
- Updated onboarding, API and testing documentation.

## 1.0.0-rc1 — 2026-11-03

- Assembled a fresh local release for the Japan-focused FactoryLink product.
- Added bilingual Japanese/English application navigation and forms.
- Added organisation-scoped authentication and business APIs.
- Added procurement, inventory, production, quality, traceability and maintenance workflows.
- Added notification and audit views, report exports and document sharing.
- Added PostgreSQL, Redis, Celery, Docker Compose, Nginx and Alembic configuration.
- Added local demo seed data, startup scripts and project documentation.


## RC8 — Account lifecycle

- Added one-time password-reset links with hashed token storage, 30-minute expiry, single-use redemption and revocation of every active refresh-token family on password change.
- Added workspace-admin invitations with role validation, inactive accounts until acceptance, seven-day expiry, one-time redemption and automatic sign-in after acceptance.
- Added SMTP delivery through the Celery worker and explicit development-only action links for local testing when SMTP is not configured.
- Added production startup requirements for SMTP configuration and disabled development action links.
- Added Nginx throttling for password-reset request/confirm and invitation-accept routes.
- Replaced frontend direct-password user creation with the invitation workflow and added bilingual forgot-password/reset/invitation screens.


## RC9 — Supplier workspace administration

- Supplier workspace registration now creates a `SUPPLIER_ADMIN` owner account.
- Supplier administrators can list users in their own workspace and send one-time invitations to `SUPPLIER_USER` colleagues.
- Supplier administrators share the supplier-only operational boundary with supplier users; they do not gain manufacturer inventory or operations permissions.
- Added regression tests for supplier workspace owner role, member invitation, supplier purchase-order visibility and denial of manufacturer inventory access.
- Corrected the test login fixture for supplier administrators.
- Verification: **48 backend tests passed** on isolated SQLite; Python compilation, frontend TS/TSX syntax transpilation, Compose YAML structure and shell syntax checks passed. Docker/PostgreSQL runtime and dependency-backed Vite/browser tests remain unverified here.


## RC10 — Full-stack source integration hardening

- Fixed the inventory receipt modal's undeclared purchase-order state, which blocked a real TypeScript build.
- Added release-integrity tests for fixed frontend API routes, the receipt modal's state contract and Compose owner/runtime database separation.
- Hardened the repeatable PostgreSQL database bootstrap: broad table writes are revoked on each run, only reviewed workflow-column updates are reapplied for existing tables, future-table defaults remain read/insert-only, and Alembic history writes are revoked after global grants.
- Expanded the PostgreSQL runtime-role acceptance script to assert role flags and expected/forbidden column and table privileges.
- Verification in this environment: 56 backend tests pass; fresh SQLite migrations and idempotent seeding pass; live Uvicorn smoke passed for factory dashboard and supplier purchase orders; fixed frontend API route contract passed; TypeScript semantic/source checks passed with temporary declaration shims.
- Not verified here: Docker/PostgreSQL runtime, PostgreSQL RLS/ACL script execution, dependency-backed Vite build, browser E2E, SMTP delivery and deployment. Docker is unavailable and the npm registry could not be resolved.

## RC12 — PostgreSQL and background-worker acceptance foundation

- Added a PostgreSQL 17 + Redis GitHub Actions service job.
- Added a repeatable acceptance runner that bootstraps and rechecks the least-privilege runtime role, applies migrations, seeds demo data, validates RLS/ACL behavior, starts the API as the restricted role, and executes a tenant-aware Celery task through Redis.
- Expanded RLS assertions to verify missing tenant context returns no operational rows and that supplier accounts cannot see unrelated supplier workspace records or their purchase orders.
- Added a live runtime API smoke for factory dashboard/inventory, supplier purchase-order visibility and inventory denial, refresh rotation, language update, and post-commit tenant-context reapplication.
- Local environment still lacks Docker/PostgreSQL/Redis services, so the new real-service acceptance job is configured but has not yet executed from this environment.


## RC12 — PostgreSQL receipt progress and runtime acceptance

- Persisted factory-confirmed cumulative purchase-order receipt totals so supplier accounts can view partial delivery progress without access to factory inventory ledgers.
- Added migration `0006_supplier_receipt_progress` with immutable-ledger backfill, a quantity-bounds constraint, and a PostgreSQL trigger restricting counter changes to the PO-owning factory tenant.
- Tightened supplier PO RLS to require the supplier record and purchase order to belong to the same factory.
- Extended the PostgreSQL API smoke to exercise PO creation, supplier confirmation/dispatch, linked partial goods receipt and supplier-visible receipt totals under the restricted runtime role.
- Added PostgreSQL 17 + Redis acceptance to GitHub Actions, including RLS/ACL, API and Celery worker checks.
- Local verification: 64 backend tests passed; SQLite fresh and RC11 upgrade migrations, repeated seed and live API smoke passed. Actual PostgreSQL/Docker/Redis and Vite/Playwright browser runtime remain unverified in this build environment.


## RC14 — Production hardening

- Added server-generated request correlation IDs and JSON HTTP access logging that excludes credentials, headers, request bodies and query strings.
- Added internal Prometheus-format request counters/duration totals and separate liveness/readiness endpoints.
- Changed Compose backend healthcheck and local startup wait to use dependency-aware readiness.
- Added PostgreSQL custom-format + uploaded-file backup scripts for Bash and PowerShell, SHA-256 verification, retention, explicit restore confirmation and upload-volume rollback preservation.
- Added localhost-restricted k6 read-path smoke profile and operational backup/load documentation.
- Verified 73 backend tests, clean SQLite migration/seed, and live API liveness/metrics/login; Redis readiness correctly reported unavailable on this runner.


## RC15 — Production configuration hardening

- Fail closed in production unless the database uses PostgreSQL via Psycopg 3 with TLS enabled.
- Require HS256 JWT configuration and exact HTTPS CORS origins.
- Require SMTP STARTTLS and paired SMTP credentials.
- Add a restrictive SPA Content Security Policy, cross-origin isolation headers and conditional HSTS from a trusted HTTPS edge.
- Add production-startup regression tests for unsafe transport and cryptographic settings.
