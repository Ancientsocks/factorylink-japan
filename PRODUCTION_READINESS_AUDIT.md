# FactoryLink Production Readiness Audit

## Code-level update — 2026-11-23

This pass addressed the repository-controlled items that previously made the
project's own CI fail, without changing any deployment, database, storage or
mail configuration:

- Security-pinned dependencies refreshed: FastAPI 0.165.0 (Starlette 1.10.0),
  PyJWT 2.15.1, python-multipart 0.0.34, pydantic-settings 2.14.2; Vite 7.3.8,
  Vitest 5.1.1. `pip-audit` and `npm audit --audit-level=high` now report no
  known vulnerabilities.
- Backend regression **155 passed**; frontend **8 passed** plus a production
  Vite build; local acceptance runner **5 passed / 0 failed / 6 skipped**.
- Stale release-integrity tests for the deleted `render-database.yaml` were
  replaced with checks for the staged two-step single Blueprint.
- Committed `.bak` file copies were removed; generated `*.tsbuildinfo` files
  are now ignored.

The release decision below is unchanged: these results are not deployment,
recovery or customer-acceptance evidence. Docker runtime, live PostgreSQL/Redis/
Celery, Playwright journeys, Render sync, private S3, SMTP, monitoring/alerting,
backup/PITR and Japanese customer acceptance remain outstanding.

## Current evidence update — 2026-11-05

The older verification notes later in this file describe an earlier blocked
Docker session and a previous database revision. They are historical, not the
current local status. The local application was subsequently upgraded to
Alembic `0011_inventory_reconciliation`; backend readiness, PostgreSQL, Redis,
malware-scanner and frontend health checks passed. Isolated staging recorded
three browser journeys, the full procurement-to-shipment traceability workflow,
Redis rate-limit checks, migration failure/recovery, and a separate-database
backup/restore drill. A preliminary five-user/25-operation load run had zero
failed requests or operations and p95 around 145 ms; it is not a capacity/SLO
certification. The previous full backend suite recorded 152 passes; this
packaging pass separately ran 51 focused Render/release-integrity tests.

Production is **still not approved**. SMTP delivery, real Render deployment,
private S3 acceptance, provider-side backup/PITR and restore, external monitoring
and alert delivery, Japan/Singapore processing approval, and customer factory
acceptance remain unverified. See `RELEASE_REVIEW_2026-11-05.md` for the current
Render-specific source changes and release gates.


**Review date:** 2026-11-05  
**Release decision:** **NOT PRODUCTION-READY**

## Scope and evidence standard

Reviewed production-critical application and operations paths: authentication,
authorization, tenant scoping/RLS migrations, manufacturing API/models,
uploads/scanning/storage, background tasks, production Compose/reverse proxy,
CI, database bootstrap, backup/restore/load scripts, localization, and the
acceptance evidence in this workspace. The findings below distinguish source
inspection from tests and external configuration. This is not a certification,
penetration test, legal opinion, or proof of a cloud/provider configuration.

The 2026-11-05 continuation verified Docker connectivity, completed a
read-only inventory, and exercised the latest production-tagged application
images in isolated staging. The existing `factorylink` development project
was not changed. Staging migrations, readiness, restricted-role PostgreSQL
acceptance/RLS, Redis rate limiting, concurrent inventory reconciliation,
migration failure/recovery, browser journeys, a local PostgreSQL/uploads
restore drill, bounded load, and Celery idempotency/retry were exercised.
The detailed evidence and limits are in [TESTING.md](./TESTING.md). A prior
security review reported no exploitable vulnerability findings; that review
does not replace an independent penetration test.

## P0 — Critical security, data-loss, or functionality blockers

| Finding | Evidence and required closure |
|---|---|
| The existing development backend image does not recognize its database revision. | Read-only `docker exec factorylink-backend-1 alembic current` fails with `Can't locate revision identified by '0009_finished_product_quality'`. The existing development DB remains at `0009`; the current source head is `0011_inventory_reconciliation`. In isolated project `factorylink-staging-20261105-0108`, the rebuilt production backend/frontend images started on distinct PostgreSQL, Redis, and uploads volumes; both `alembic current` and `alembic heads` reported `0011_inventory_reconciliation`, and readiness returned HTTP 200 with database and Redis `ok`. The staging compatibility blocker is resolved, but the existing development-container mismatch remains intentionally untouched and must not be mistaken for a deployment. |

No additional P0 issue was established by the source review. This does not
clear the release gates below.

## P1 — Required before a real company deployment

| Finding | Evidence and required closure |
|---|---|
| No customer-specific staging rollout or production operation has been evidenced. | The distinct Compose topology and procedures exist, but DNS, Caddy/ACME, PostgreSQL TLS, SMTP, private S3, ClamAV, secrets, firewall, monitoring, alert delivery, migration ordering, and rollback have not been demonstrated together in an isolated customer-like environment. Complete and record staging acceptance before production. |
| PostgreSQL tenant isolation, Redis rate limiting, and reconciliation require live integration evidence. | The isolated staging PostgreSQL acceptance passed using restricted runtime role `factorylink_app`, including tenant RLS and least-privilege checks, cross-tenant negative paths, complete procurement-to-shipment/traceability workflow, and concurrent inventory adjustment/reconciliation. Real Redis rate-limit checks passed enforcement, client isolation, and expiry. The test scripts use staging-only data. |
| Production backup scheduling and encrypted S3 recovery remain unverified. | A real staging-local `pg_dump`/restore into a separate disposable database and an uploads archive/restore to separate scratch storage passed; migration revision, selected row counts, and document SHA-256 matched. The scheduled production backup path using age, S3, KMS, retention, provider PITR, and alerting was not exercised; configure and drill it with customer-owned provider credentials before release. |
| Monitoring and alert delivery are not provisioned. | `/metrics` is process-local; Compose does not provide a collector, durable log store, alert manager, or alert route. Readiness checks cover database, Redis, and enabled ClamAV, not SMTP, S3, worker/scheduler liveness, backup success, or queue health. Configure private external monitoring and prove alert delivery; see [PRODUCTION_OPERATIONS_RUNBOOK.md](./PRODUCTION_OPERATIONS_RUNBOOK.md). |
| Load/capacity and service objectives are only measured for one bounded staging profile. | The 5-user, 25-operation, 60-second staging run completed 85 HTTP requests in 56.103 seconds (1.52 requests/second), with 0 request/operation failures, p95 144.98 ms (1,000 ms configured ceiling), and HTTP statuses 65×200 / 20×201. A single `docker stats` sample during the run showed backend 10.37% CPU / 93.67 MiB, PostgreSQL 7.20% / 88.45 MiB, and Redis 2.26% / 3.801 MiB. This is a bounded sample, not a capacity/SLO certification or peak profile; test representative customer workloads and agree limits, capacity, RPO/RTO, and retention. |
| Migration evidence does not yet cover the release matrix. | `scripts/db/migration-safety.py` passed in isolated staging: empty install, populated `0009` predecessor upgrade, controlled `0011` grant failure with rollback, successful retry, data preservation, and schema/index/constraint/RLS checks using disposable staging databases. `0001_initial.py` still builds from live model metadata, and downgrades are not presumed safe. |
| Background reminder retries and duplicate deliveries need live PostgreSQL verification. | In staging, two additional reminder deliveries both returned `notifications_created: 0`; the count of `Maintenance reminder` notifications remained 2. A queued email task with SMTP intentionally unset produced no outbound email, retried five times in the real Celery worker, then reached the expected terminal `RuntimeError`. This verifies configured retry behavior but not a real SMTP provider or transient SMTP recovery. |
| Japanese acceptance, residency, and privacy decisions remain customer-specific. | English/Japanese dictionaries, JPY formatting, and `Asia/Tokyo` display/task settings are present. Translation completeness, backend error wording, customer terminology, rounding/fiscal practices, and timezone edge cases need Japanese-speaking user acceptance. The Render blueprint places services in Singapore; the Compose topology does not itself select the database, mail, logs, backup, or support-access region. Obtain customer decisions and qualified privacy/legal review; no certification is claimed. |
| CI configuration is not execution evidence. | CI contains backend/frontend tests, builds, dependency audits, PostgreSQL and browser jobs; this review added a production Compose validation/image-build job. The Compose render and production backend/frontend image builds passed locally, but no successful GitHub Actions run or dependency scan result was available. Require a green CI result for the release source and retain its artifact/log evidence. |

## P2 — Improvements that can follow initial release

| Finding | Evidence / follow-up |
|---|---|
| Numeric storage uses binary floating point. | Purchase-order prices and manufacturing/inventory quantities use SQL `Float`. Plan reviewed fixed-precision monetary and quantity types, rounding policy, migration, and reconciliation before financial scale or high-precision process use. |
| The initial migration is not a frozen historical schema. | `backend/migrations/versions/0001_initial.py` imports current models and calls `Base.metadata.create_all`. Current follow-on migrations include guards, but future model edits can still affect fresh-install replay. Replace or freeze the baseline through a reviewed migration strategy. |
| Reminder deduplication still relies on an application-level identity. | Production reminder deliveries now serialize with a PostgreSQL advisory lock and retry/redelivery checks the tenant's existing notification before inserting. A database uniqueness constraint or stable idempotency key would make this invariant independently enforceable. SMTP retries may also duplicate messages when delivery succeeds but acknowledgement is lost. |
| Supporting-image hardening and supply-chain pinning can improve. | Backend/frontend run non-root by their image definitions. Redis, Caddy, and ClamAV effective users/capabilities are not pinned or verified here; images use version tags rather than immutable digests. Verify compatibility, harden, and pin/refresh reviewed digests. |
| Audit retention and operational ownership are unspecified. | Audit events exist, but customer retention, access, export, legal hold, deletion, and incident ownership policies are not configured by this repository. Agree these policies and monitoring ownership before onboarding production data. |

## Implemented and verified by source inspection

- Passwords use PBKDF2-HMAC-SHA256 (310,000 rounds). Access JWTs expire;
  refresh-token digests are stored, rotations are tracked, and replay revokes
  the affected login family. API role checks read the current database role.
- PostgreSQL tenant context is set transaction-locally from the signed
  organization claim. Migrations cover operational and identity tables; the
  production bootstrap creates a restricted, non-superuser runtime role and
  grants selected update columns. Live role/RLS acceptance is still required.
- Business routes implement supplier/PO receipt flow, lot inventory and
  reason-coded movements, FIFO reservation/consumption, production progress,
  quality inspection/holds/CAPA/release, finished-batch/serial genealogy and
  shipment, maintenance tasks/reminders, notifications, and audit records.
  Prior acceptance evidence for these paths is summarized in `TESTING.md`;
  this source review alone does not establish operational correctness.
- Upload handling applies size/type/signature checks and scans before storage.
  Production startup requires S3-compatible storage and enabled malware
  scanning; scanner failures reject uploads.
- Production settings reject weak/default JWT keys, wildcard/non-HTTPS CORS,
  non-TLS PostgreSQL URLs, public registration, demo seeding, exposed auth
  action links, insecure SMTP, local storage, and disabled malware scanning.
- Request limits cover all API routes and separate authentication,
  registration, password-reset, and invitation buckets. Production requires
  Redis rate limiting to fail closed. Reminder delivery is retryable and
  protected against duplicate concurrent execution.
- `docker-compose.production.yml` is distinct from the evaluation stack. It
  exposes only the Caddy edge; database and object storage are external.
  Backend and frontend images are non-root by their Dockerfiles; named volumes
  persist Redis, ClamAV state, uploads, and Caddy state.
- The frontend proxy sets browser security headers/CSP and disables access
  logging; production FastAPI docs/OpenAPI routes are disabled. The application
  uses bearer tokens in session storage rather than cookie authentication.
- `.env` and `.env.production` are ignored by `.gitignore`; the production
  example contains placeholders. The filled local `.env` was not read. This
  workspace is not available as a Git repository, so tracked-secret history
  could not be established here.
- CI definitions request backend/frontend validation, dependency audits,
  PostgreSQL acceptance, browser journeys, and Docker checks. The production
  Compose validation/build is now added but still requires a successful CI run.

## Verification completed in this review

- Re-inspected the current staging/production Compose and migration source.
  Docker container/image inspection failed because the Docker Desktop Linux
  engine pipe is unavailable. No container was started and no database or
  volume was changed.
- The VS Code test controller did not discover Python tests. The configured
  workspace Python was used through a VS Code task instead.
- Focused backend/API/rate-limit/task/release-integrity tests passed; the exact
  final count is recorded in [TESTING.md](./TESTING.md).
- PostgreSQL, Redis service integration, staging, backup/restore, and load
  acceptance were not run because Docker is unavailable and no external
  PostgreSQL/Redis, S3, or backup credentials were supplied.
- Production Compose rendered successfully with `.env.production.example`;
  no services were started.
- Production backend and frontend container images built successfully. The
  frontend image build ran its `npm ci` and `npm run build` steps. Neither
  image was started or deployed.
- Backend suite: **140 passed**, 1 upstream Starlette/AnyIO deprecation
  warning. The first run exposed a stale release-integrity assertion expecting
  `npm install`; it was corrected to require lockfile-based `npm ci`, then the
  complete backend suite passed.
- Frontend unit suite: **8 passed** across 2 files.
- Playwright browser journeys: **5 passed** against the test fixture's
  temporary SQLite database.
- PostgreSQL/RLS, Redis/Celery, dependency scans, backup/restore, load, and
  customer staging were not run in this review.

## Release status and required gate

**Implemented and locally verified:** Reconciliation lock-order and
idempotent reminder changes passed focused backend tests. The previous review's
backend (140), frontend (8), Playwright (5), production Compose render, and
image build evidence remains historical and is recorded in [TESTING.md](./TESTING.md).

**Implemented but not verified against services:** Tenant RLS, Redis rate
limits, concurrent reconciliation, migration recovery, scheduled encrypted
backup, reminder duplicate protection, and bounded load testing have code or
acceptance harnesses. The new live PostgreSQL/Redis/Celery/migration checks,
staging deployment, backup/restore drill, and workload have not run in this
session. Source presence is not deployment or recovery evidence.

**Remaining before production:** Resolve the P0 image/schema mismatch in a
uniquely named isolated staging stack; run the PostgreSQL runtime-role/RLS,
Redis/Celery, migration-safety and concurrent-workflow acceptance; complete a
full PostgreSQL/document restore drill; run the new staging load test; and
record staging/rollback evidence. Provision DNS, cloud/database/storage/email
credentials, external monitoring/alerts, data-residency/privacy decisions,
RPO/RTO, and customer approval. Do not deploy publicly or use real customer
data until these gates pass.
