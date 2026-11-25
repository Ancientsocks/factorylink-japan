# Deployment Guide

## Local Docker Compose

Compose starts PostgreSQL and Redis, creates a restricted `RUNTIME_DB_USER`, runs Alembic migrations and optional seed data with the database owner, then starts FastAPI and Celery using only the restricted runtime database role. The runtime role has no superuser, database-creation, role-creation or schema-ownership privileges. The API role receives DML on application tables plus transaction-local RLS policies; it does not receive write privileges on Alembic's migration-version table.

Prerequisites: Docker Desktop (Windows/macOS) or Docker Engine plus the Compose plugin (Linux), with at least 4 GiB RAM available for ClamAV. The first run needs access to container registries and package registries; initial ClamAV signature loading may take several minutes.

```bash
cp .env.example .env
# Edit .env: use strong POSTGRES_PASSWORD and RUNTIME_DB_PASSWORD values and a random JWT_SECRET_KEY
docker compose up --build -d
docker compose ps
docker compose logs -f backend
```

Open `http://localhost:8080`. Only the frontend service is published to the host. PostgreSQL, Redis, ClamAV and internal API ports remain on the Compose network. Compose starts nine services; API readiness requires PostgreSQL and Redis plus ClamAV PING when malware scanning is enabled. `/health/live` remains a process-only liveness probe.

## Production configuration checklist

1. Set `ENVIRONMENT=production`; keep `POSTGRES_USER`/`POSTGRES_PASSWORD` for migration administration only and set separate strong `RUNTIME_DB_USER`/`RUNTIME_DB_PASSWORD` credentials for API and workers.
2. Set `JWT_SECRET_KEY` to a randomly generated secret with at least 32 bytes of entropy and set `JWT_ALGORITHM=HS256`. Keep the key in the platform secret manager, not in a source file.
3. Set exact `https://` trusted `CORS_ORIGINS`; do not use wildcard or HTTP origins with credentials.
4. Set `DATABASE_URL` to the SQLAlchemy Psycopg 3 form (`postgresql+psycopg://...`) and require TLS with `?sslmode=require` (or `verify-ca` / `verify-full` where CA verification is configured). Percent-encode reserved characters in the URL username/password. The application refuses SQLite, non-Psycopg URLs and unencrypted PostgreSQL connections in production.
5. Use a managed PostgreSQL service with encrypted connections, automated backups, point-in-time recovery and tested restores.
6. Use managed Redis or a properly secured private Redis service.
7. Put the app behind HTTPS and a trusted reverse proxy/WAF. The edge must overwrite client-supplied `X-Forwarded-Proto`; Nginx emits HSTS only when it receives `X-Forwarded-Proto: https`. The React app receives a restrictive Content Security Policy; Swagger `/docs` is kept separate because its initializer requires inline script execution.
8. Configure a private malware-scanning service for attachments, then private S3-compatible object storage. Production startup rejects `STORAGE_PROVIDER=local`. Set `STORAGE_PROVIDER=s3`, `STORAGE_S3_BUCKET`, `STORAGE_S3_REGION`, and either a paired access-key/secret pair or a cloud workload identity. `STORAGE_S3_ENDPOINT_URL` is optional and must be HTTPS in production. Use a private bucket with Block Public Access enabled, Bucket owner enforced (ACLs disabled), versioning, and default SSE-S3 or SSE-KMS encryption. Grant the API identity only `s3:PutObject`, `s3:GetObject` and `s3:DeleteObject` on the bucket's object ARN; no public ACL, `s3:ListBucket`, bucket administration or account-wide permissions are required. The API streams downloads only after its organisation/supplier authorization check.
9. Set `SEED_DEMO_DATA=false` and `ALLOW_PUBLIC_REGISTRATION=false`. Production startup refuses to run if demo seed data or open workspace registration is enabled. One-time password-reset and colleague-invitation delivery use SMTP/Celery, and workspace registration plus forgotten-password recovery now require a six-digit code emailed to the address before a password can be set, so SMTP must be working before sign-up or account recovery can complete.
10. Forward JSON access logs to a centralized log service; configure alerting, error tracking, rate limiting and operational monitoring. Request logs include a server-generated `X-Request-ID`, method, route template, status and duration only; credentials, headers, bodies and query strings are not logged.
11. Scrape `/metrics` from a private monitoring network only. The endpoint is intentionally not proxied by the public Nginx frontend and currently reports per-process counters; aggregate it across replicas in the monitoring system.
12. Use `/health/live` for liveness and `/health/ready` for readiness. Readiness requires database and Redis connectivity plus ClamAV PING when malware scanning is enabled.
13. Test worker and scheduler operations, retention policies and disaster recovery.
14. Run positive and negative PostgreSQL RLS tests for every tenant table, including linked supplier operations and notification/document sharing.
15. Complete security, privacy and Japanese business-process review before onboarding real customers.


### Malware scanning (required for customer uploads)

Docker Compose includes the official `clamav/clamav:1.5` image. The API sends validated, size-bounded upload bytes to `clamd` with INSTREAM and persists the object only after `stream: OK`. A malware finding returns 422; scanner unavailability, timeout or an invalid response returns 503 without creating an object or attachment row. The backend readiness probe checks clamd PING whenever scanning is enabled.

- Keep `MALWARE_SCAN_ENABLED=true`, `MALWARE_SCANNER_HOST` set to the private ClamAV host, `MALWARE_SCANNER_PORT=3310` and the timeout configured. Production startup refuses disabled/unconfigured scanning.
- The Compose service uses a persistent `clamav_database` volume to retain signature databases. Allow its first database load/update to complete before the API becomes ready. Allocate at least 4 GiB RAM for the scanner container/service; ClamAV documentation warns that 2 GiB may be insufficient.
- Do not publish TCP 3310 or expose the scanner to the public internet. ClamAV's TCP protocol is unencrypted and unauthenticated; keep the scanner and API on one private network only.
- For Render, the application-services Blueprint provisions a separate private service from `scanner/Dockerfile` in the same region/network, allocates 4 GiB RAM and persistent storage for `/var/lib/clamav`, and wires the scanner's private hostname into the API automatically. The scanner is intentionally not public.
- On AWS, run a private scanner task/service (or an approved managed malware-scanning product) in the API private subnets/security group. Permit only API-to-scanner TCP 3310. Keep the scanner image and signature updates current.
- Before go-live, run a controlled EICAR test file through the upload route and verify HTTP 422, no S3/local object and no attachment row; stop the scanner and verify HTTP 503 with no persisted data; restore the scanner and verify a clean test document uploads/downloads successfully. Never use live malware samples.

Reference: [ClamAV Docker deployment](https://docs.clamav.net/manual/Installing/Docker.html) and [ClamD protocol](https://docs.clamav.net/manual/Usage/ClamdProtocol.html).

## Render production Blueprint

FactoryLink uses one Render Blueprint at the repository root, `render.yaml`, and syncs it in two stages. The first version defines only PostgreSQL. After the database is healthy and its restricted runtime credential is created, the same Blueprint is expanded with the application services. Do not create a second Blueprint for the application.

All services currently use Singapore because Render does not list a Japan region. The full application configuration is temporarily staged at `deploy/render-services.pending.yaml`; do not choose that file as the Blueprint path.

### Stage 1 — Provision PostgreSQL

1. In Render, choose **New → Blueprint** and connect the private repository `Ancientsocks/factorylink-japan`, branch `main`. Keep the Blueprint path as `render.yaml`.
2. Confirm the proposed change shows exactly one database and no application services:
   - Resource: `factorylink-postgres`
   - Database: `factorylink`
   - Initial user: `factorylink_owner`
   - Region: Singapore; PostgreSQL 17
   - Plan: `0.5c-1g`; storage: 15 GB
   - External IP allow-list: empty
3. Review pricing and deploy the Blueprint. Wait until PostgreSQL is available.
4. Copy its **Internal Database URL** for `factorylink_owner` and store it securely as `OWNER_DATABASE_URL`. Save it before rotating the default credential.
5. In the database Credentials section, create a new default credential named `factorylink_app`. Confirm it is the active default. The owner credential remains valid for the one-time migration step.

### Stage 2 — Add application services to the same Blueprint

1. After Stage 1 is complete, the full app configuration in `deploy/render-services.pending.yaml` will be copied into the root `render.yaml` and committed. Keep using the existing Blueprint and the same root file path. Let Auto Sync apply the newly added resources, or choose Manual Sync if Auto Sync is disabled. Do not create another Blueprint.
2. Review the change list. It should add the private FastAPI API, public Nginx/React web service, private Key Value, private ClamAV, Celery worker and scheduler. The existing PostgreSQL resource must remain the same; do not approve a second database or replacement.
3. Supply the saved `OWNER_DATABASE_URL`, HTTPS `FRONTEND_BASE_URL`, matching `CORS_ORIGINS`, SMTP host/credentials/sender, and private S3 bucket credentials when prompted. Configure SMTP for the worker too. Keep secrets in Render's secret environment settings, never in Git.
4. After all services are healthy, open a Shell on `factorylink-api` and run:
   ```bash
   python -m app.render_deploy bootstrap-admin
   ```
   Follow the prompts to create the first manufacturer workspace and administrator. Use a unique password of at least 14 characters. This is a one-time operation; subsequent employees should be invited by the administrator.
5. Verify readiness, login, employee invitations, password reset, clean-file upload/download, EICAR rejection, scanner outage handling, tenant/supplier isolation and core manufacturing workflows before customer onboarding.

Before real uploads, provision a private S3 bucket in the customer-approved region, with Block Public Access, bucket-owner-enforced object ownership, versioning and default encryption. Use a dedicated IAM identity limited to the required object operations on this bucket. The Blueprint does not configure off-site backups, tested restore, S3 retention, provider PITR, monitoring/alerts or SMTP domain authentication; these are separate production gates.

Render currently lists Singapore, Frankfurt and US regions, not Japan. Japanese data residency and cross-border processing must be explicitly approved by the customer and their qualified privacy/legal reviewer before real factory data is stored. A custom domain is optional for initial staging; use the Render-provided HTTPS address first.

References: [Render Blueprints](https://render.com/docs/infrastructure-as-code), [Blueprint specification](https://render.com/docs/blueprint-spec), [PostgreSQL credential rotation](https://render.com/docs/postgresql-credentials), and [available regions](https://render.com/docs/regions).

**Deployment status:** no Render resource has been created from this Blueprint yet. A successful source review is not evidence of a live deployment or customer acceptance.

## AWS deployment outline

For AWS, use a private ECS service or EC2 deployment behind an Application Load Balancer, with RDS PostgreSQL, ElastiCache Redis, a private S3 bucket for attachments, IAM roles and Secrets Manager. Give the API task role only `s3:PutObject`, `s3:GetObject` and `s3:DeleteObject` on the one bucket's object ARN. The Boto3 default credential chain uses the ECS task role/EC2 instance profile when explicit storage keys are blank. Keep the migration owner credential scoped to the migration task only; API and worker tasks use the restricted runtime role. Do not expose database or Redis ports publicly. The AWS topology is documented but has not been deployed or verified from this repository.

## Verify database role and RLS policies

After a local demo stack is running, use a PostgreSQL owner connection to run `scripts/db/verify-runtime-role.sql` and `scripts/db/verify-rls.sql` (see `TESTING.md` for the psql variables and what each script asserts). These checks require the fictional demo tenants; do not run the RLS demo script against a customer database. The RLS script rolls back its test transaction.

## Migration/runtime separation

Do not point the API or Celery services at the migration owner account. The Compose stack creates a non-owner runtime role and runs Alembic with `POSTGRES_USER` only in the one-shot migration service. For non-Compose deployments, create an equivalent runtime role with only required table DML and sequence usage, no `BYPASSRLS`, no table ownership, and no DDL privileges. Keep the migration credential in a separate job/secret scope.

## Backups and recovery

The local Compose backup scripts save both the PostgreSQL database and the uploaded-document volume. Each backup folder contains `database.dump` (PostgreSQL custom format), `uploads.tar.gz`, `SHA256SUMS` and `BACKUP_INFO.txt`. Backups contain sensitive personal, supplier and operational data: the Linux script creates private directories/files (`umask 077`); keep the backup location encrypted at rest, access-controlled and outside source control. `.backups/` is git-ignored.

Linux/macOS (Bash):

```bash
./scripts/backup/backup.sh
(cd .backups/factorylink-YYYYMMDDTHHMMSSZ && sha256sum -c SHA256SUMS)
./scripts/backup/restore.sh .backups/factorylink-YYYYMMDDTHHMMSSZ --confirm
```

Windows PowerShell:

```powershell
.\scripts\backup\backup.ps1
.\scripts\backup\restore.ps1 -BackupDirectory .backups\factorylink-YYYYMMDDTHHMMSSZ -ConfirmRestore
```

Restore replaces the target database contents and uploaded files. Stop external traffic and restore into an isolated environment unless a rollback is intentional. The scripts verify checksums, reject unsafe archive paths, preserve the current database and uploads as pre-restore files, stop frontend/worker/scheduler/backend services in a controlled order, reapply the runtime database role grants, apply pending Alembic migrations without demo seeding, and then restart app services. If a restore fails, app services remain stopped for recovery; use the printed pre-restore database dump and upload archive to roll back. The scripts do not encrypt backup archives. Configure encrypted storage and managed off-site copies, and perform regular restore drills. For production, prefer managed PostgreSQL point-in-time recovery plus separately backed-up encrypted object storage; a volume snapshot alone is not a verified backup strategy. The local Compose backup scripts archive the local uploads volume only; they do not export an S3 bucket. Configure S3 versioning and a tested replication/lifecycle/backup plan separately, and perform an object-level restore drill that verifies attachment hashes and database references.

## Load smoke test

Install [k6](https://k6.io/docs/get-started/installation/) on the test host and use a dedicated low-privilege test account. The default target is restricted to localhost:

```bash
LOAD_TEST_EMAIL=load-test@factorylink.local LOAD_TEST_PASSWORD='change-this-test-password' \
  k6 run scripts/load/k6-smoke.js
```

Defaults are 5 virtual users for 30 seconds, with a 1% maximum error-rate threshold and a 95th-percentile latency threshold of 1 second. Start with low values and increase only on an isolated test environment. To target a remote environment, explicitly set `ALLOW_EXTERNAL=1` and confirm written authorization from its owner. Do not run load tests against a customer production tenant without a scoped test plan.


## Transactional email configuration

Sign-up and forgotten-password recovery email a six-digit code, so email delivery is a hard requirement in production.

**SMTP:** set `SMTP_HOST`, `SMTP_PORT` (normally 587), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS=true`, and `FRONTEND_BASE_URL` to the HTTPS application URL. These settings are read by the API and the Celery worker. In production set `EXPOSE_AUTH_ACTION_LINKS=false` and `SMTP_STARTTLS=true`; the API refuses plaintext SMTP, requires both SMTP credentials together if authentication is used, and refuses to expose raw action tokens in API responses.

**Resend (HTTPS, optional):** set `RESEND_API_KEY` and `RESEND_FROM` to a verified sender. When present this channel takes precedence over SMTP and needs no worker or outbound SMTP port. Either way, send yourself a test code from the sign-up screen before considering account recovery operational, and check the API log for `Email delivery to ... failed` if it does not arrive.

Delivery behaviour: production queues through Celery and falls back to a direct send when the broker is unavailable; development sends directly so a missing worker never silently loses a code. With no channel configured the API returns `email_sent: false` (registration) and, in development only, the code itself.

### Google sign-in (optional)

1. In Google Cloud Console create an OAuth 2.0 Client ID of type *Web application*.
2. Add the authorised redirect URI that matches `GOOGLE_REDIRECT_URI` exactly (for example `https://app.example.jp/api/v1/auth/google/callback`; local development defaults to `http://127.0.0.1:8000/api/v1/auth/google/callback`).
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Both must be set together; production additionally requires an HTTPS redirect URI and rejects a half-configured client at startup.
4. The UI hides the Google button unless `/api/v1/auth/providers` reports it enabled.

Google proves the email address, so a new Google user is taken to a workspace-details form instead of the email-code step; existing accounts sign in directly. Google-only accounts have no password and can set one later through the code-based password reset.


### Runtime grants on restart

`db-bootstrap` is intentionally repeatable and runs before `migrate`. On an existing database it removes table-wide `UPDATE`/`DELETE`, then restores only reviewed per-column workflow updates for tables already present, plus `DELETE` on the six record tables staff may clear from the operations screens (`suppliers`, `purchase_orders`, `production_orders`, `equipment`, `maintenance_tasks`, `attachments`). Audit, ledger and inspection history remain append-only. This matters because PostgreSQL's `REVOKE` of a table-level privilege also removes the corresponding column-level privilege. Alembic version-table writes are revoked after the global SELECT/INSERT grant. Run `scripts/db/verify-runtime-role.sql` and `scripts/db/verify-rls.sql` against the running Postgres instance after the first start and after an ordinary restart.
