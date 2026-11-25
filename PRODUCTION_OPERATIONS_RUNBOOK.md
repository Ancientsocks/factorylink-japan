# Production operations runbook

This runbook is a template for an operator-approved environment. It does not
claim that a provider, alert route, schedule, or recovery objective is currently
configured. Test all procedures in staging first.

## Latest isolated staging verification — 2026-11-05

Docker 29.8.1 / Docker Desktop 4.93.0 / Compose 5.5.1 were reachable. The
read-only inventory identified the existing `factorylink` development project
and its database, Redis, uploads, and ClamAV volumes; the development database
had 3 organizations, 8 users, and Alembic revision
`0009_finished_product_quality`. No development services, records, or volumes
were modified. The existing backend container remains unable to locate
revision `0009_finished_product_quality`; do not run migrations or replace its
image without an approved development change.

Isolated Compose project `factorylink-staging-20261105-0108` used separate
PostgreSQL, Redis, and uploads volumes. Production-tagged backend and frontend
images migrated fresh staging to `0011_inventory_reconciliation`; Alembic
current/head matched and `/health/ready` returned HTTP 200 with database and
Redis `ok`. The restricted-runtime-role PostgreSQL workflow/RLS, Redis rate
limit/expiry/isolation, concurrent inventory/reconciliation, empty/prior
revision migration and failure/recovery, three browser journeys, local restore,
bounded load, and Celery idempotency/retry checks passed as detailed in
[TESTING.md](./TESTING.md).

The staging-local database and uploads restore passed, but the production
scheduled age/S3/KMS backup pipeline, customer SMTP, external monitoring and
alerting, provider PITR, and customer-specific deployment have not been
verified. Do not treat staging results as production deployment or
certification.

## Routine checks

- Inspect service health:

  ```sh
  docker compose --env-file .env.production -f docker-compose.production.yml ps
  curl --fail --show-error https://<FRONTEND_DOMAIN>/health/ready
  ```

- Review backend, worker, scheduler, Redis, ClamAV, Caddy, PostgreSQL, SMTP
  provider, and S3 provider health/errors. Escalate failed dependencies; do not
  treat an HTTP health response as proof that backups, email, uploads, or
  scheduled jobs work.
- Verify scheduled maintenance reminders and notification delivery with a
  controlled staging/test tenant. Monitor Celery failed/retried tasks and
  scheduler liveness; avoid manually repeating non-idempotent work.
- Reminder jobs use a PostgreSQL transaction-scoped advisory lock to prevent
  overlapping deliveries. Database interface/operational failures retry with
  backoff; task delivery is late-acknowledged, and completed reminder writes
  are checked before redelivery. Monitor Celery retry/failure queues rather
  than assuming the lock or retry replaces alerting.
- Review audit events, privileged account changes, failed authentication,
  tenant access denials, and database/provider audit logs under an approved
  retention/access policy. Avoid logging tokens, passwords, sensitive query
  strings, or customer data.
- Check certificate renewal, disk and memory capacity, database storage and
  connection saturation, Redis memory/persistence, ClamAV signature updates,
  S3 errors, queue depth, and host security updates.

## Monitoring and alert ownership

The API exposes process-local request counters at `/metrics`, but the
production Compose topology does not provision a metrics collector, durable
log store, alert manager, or notification route. Do not expose `/metrics`
publicly. Before production, assign an owner and configure an approved external
monitoring service to collect the private endpoint and provider/host signals.
Test alert delivery for API/readiness failure, PostgreSQL and S3 errors,
certificate renewal, missing backups, worker/scheduler liveness, queue growth,
repeated task failures, disk pressure, and ClamAV unavailability. Set retention
and access controls for logs and metrics; keep tokens, secrets, and customer
payloads out of telemetry.

## PostgreSQL backup schedule

The application Compose file uses an externally managed PostgreSQL database;
the original `scripts/backup/backup.sh` backs up the development Compose
database and local uploads only. Production Compose now includes a separate
non-root `backup-scheduler` container. It runs the encrypted backup daily at
01:15 Asia/Tokyo by default; set `BACKUP_CRON_SCHEDULE` to the approved
customer schedule and RPO. Use provider-native automated backups/PITR as the
primary recovery layer as well.

`scripts/backup/production-backup.sh` streams a custom-format `pg_dump`
through `age`, synchronizes the current uploaded-document S3 objects into a
second encrypted archive, and uploads both archives plus SHA-256 manifests to a
private S3 backup prefix with AWS KMS server-side encryption. The source
document bucket and backup bucket must be different to avoid recursive copies.
The job requires a PostgreSQL backup account with read access to application
tables/sequences, `DATABASE_URL` using `sslmode=verify-full`,
`STORAGE_S3_BUCKET`, `BACKUP_S3_URI`, `BACKUP_AGE_RECIPIENT`,
`BACKUP_KMS_KEY_ID`, `AWS_DEFAULT_REGION`, and a least-privilege AWS workload
role. Mount the PostgreSQL CA and a secret-manager-managed shell environment
file through `BACKUP_CA_FILE` and `BACKUP_ENV_FILE`; do not commit real files
or place secrets in Compose environment values or the crontab.

Configure S3 versioning, lifecycle/retention, KMS key protection and alerts for
failed or missing uploads separately. Current-object archives complement (but
do not replace) S3 versioning and provider recovery for deleted/overwritten
objects. Define and test the RPO, RTO, retention and legal-hold policy with the
customer. A successful upload is not a restore test.

The scheduler does not prune backup objects itself. Set an approved S3
lifecycle/retention policy for the separate backup bucket, including retention
of both database and document archives and their SHA-256 manifests. Test that
the lifecycle rule cannot expire the newest recovery point before the approved
retention period. The source documents bucket and encrypted backup bucket must
remain separate.

## Isolated restore drill

1. Provision an empty database in an isolated staging account/cluster named
   with the `_restore_drill` suffix and a new, empty document directory whose
   path also ends in `_restore_drill`. Neither target may be production or
   contain existing records/files.
2. Provision AWS read access to one encrypted database object, its matching
   `-documents.tar.age` object and `.SHA256SUMS` manifest, plus a protected age
   identity file. Set `BACKUP_OBJECT_URI`, `AGE_IDENTITY_FILE`,
   `RESTORE_DRILL_DATABASE_URL`, `RESTORE_DRILL_DOCUMENT_DIR`, and
   `RESTORE_DRILL_CONFIRM=RESTORE_TO_SCRATCH_ONLY` via a protected environment.
3. Run `bash scripts/backup/production-restore-drill.sh`. It downloads and checks
   both encrypted objects, verifies archive and per-document hashes, decrypts
   into a private temporary directory, refuses databases/paths not ending in
   `_restore_drill` or with existing data, restores without `--clean`, and
   prints the restored Alembic revision.
4. Run the staging migration/current-source API, tenant-isolation suite,
   attachment/traceability checks against restored documents, and the agreed
   business smoke suite. Measure actual recovery time and record gaps.
5. Keep the staging restore for evidence only as long as approved; then have the
   DBA remove the specifically named scratch database using the provider's
   reviewed procedure. Never target or clean the live production database.

**Staging-local drill completed 2026-11-05:** a `pg_dump` was restored into the
separate disposable database `factorylink_20261105_0108_restore_drill`; both
source and restored databases reported revision `0011_inventory_reconciliation`
and matching organization/user/purchase-order/material-batch counts of
3/8/5/6. A fictional uploaded-document fixture was archived and restored to a
separate scratch directory; SHA-256 matched
`25848270ba80dfd53c68accabaffb22184f5f83e0e968acf5c8db9325a10bee5`.
This was not an execution of the production age/S3/KMS scheduler or script.
S3 document-version recovery and provider PITR must still be included in the
customer's drill.

## Database, Redis, and transaction acceptance

Run `scripts/db/postgres-acceptance.sh` only against a disposable PostgreSQL 17
and Redis service populated with the fictional acceptance seed. The runner
checks the restricted role, forced RLS for every table with
`organization_id`, identity/token tenant boundaries, the live API workflow,
concurrent inventory updates/reconciliation, real Redis throttling/expiry, and
Celery execution. Its migration-safety step creates uniquely named
`factorylink_migration_safety_*` databases, tests an empty install and an
upgrade from `0009_finished_product_quality`, induces a failed `0011` grant,
verifies transactional rollback, retries the migration, checks data/indexes/
constraints/RLS, and drops only the databases it created. Do not aim this
acceptance runner at a development or customer database.

## Bounded staging load test

Run `scripts/load-test/manufacturing_transactions.py` against an isolated
staging URL and a dedicated `ORG_ADMIN` bearer token. It drives complete
manufacturing order lifecycles (planned → ready → in progress → completed),
unique inventory receipts, and dashboard reads in a 60/20/20 mix. It caps
concurrency at 50 and logical workload operations at 2,000, paces HTTP request
starts (default 90/minute), and reports throughput, status/error counts, and
p50/p95/p99/max latency. Manufacturing operations generate finished batches
and serials; receipts generate persistent synthetic inventory and ledger
records. Use a disposable tenant and do not run the workload against
production. Set `LOADTEST_REQUESTS_PER_MINUTE` below the API's configured
limit, factoring in other test traffic; do not disable limits to make the test
pass.

Example (Linux/macOS shell):

```sh
export LOADTEST_BASE_URL=https://staging.example.invalid
export LOADTEST_BEARER_TOKEN='<dedicated-staging-token>'
export LOADTEST_USERS=10
export LOADTEST_DURATION_SECONDS=60
export LOADTEST_MAX_OPERATIONS=200
export LOADTEST_REQUESTS_PER_MINUTE=90
export LOADTEST_P95_LIMIT_MS=1000
python scripts/load-test/manufacturing_transactions.py
docker stats --no-stream
```

Record the emitted API report together with backend/container CPU and memory,
PostgreSQL connection/CPU/IO, Redis memory/latency, test image IDs, and
configured rate limits. The script cannot observe server resource usage over
HTTP. No load or recovery result should be claimed until the corresponding
staging run is completed and retained.

**Measured staging run — 2026-11-05:** 5 users, 25 logical operations, 60
seconds, 90 request starts/minute, and a 1,000 ms p95 ceiling produced 85 HTTP
requests in 56.103 seconds (1.52 requests/second), 0 failed operations, 0
request errors, p50 76.37 ms, p95 144.98 ms, p99 155.41 ms, max 193.23 ms.
The mix was 15 manufacturing operations, 5 inventory receipts, and 5 dashboard
reads; responses were 65×200 and 20×201. One `docker stats --no-stream` sample
during the run showed backend 10.37% CPU / 93.67 MiB, PostgreSQL 7.20% /
88.45 MiB, and Redis 2.26% / 3.801 MiB. This is one snapshot, not peak or
capacity evidence. A subsequent cumulative PostgreSQL stats snapshot showed
8 backends, 2,096 commits, 499 rollbacks, 2,985 inserted tuples, and 697
updated tuples; these counters were not isolated to the load interval.

**Celery staging probe — 2026-11-05:** two additional maintenance-reminder
deliveries each returned `notifications_created: 0`; the grouped notification
count remained 2 before and after. A queued email task with SMTP deliberately
unconfigured was observed in the real worker retry five times and then fail
with the expected `SMTP_HOST and SMTP_FROM must be configured` error. This
verified retry exhaustion without sending email; it does not verify a real
SMTP provider or successful transient recovery.

## Incident response / restore decision

1. Declare the incident, name the incident lead and recorder, preserve relevant
   logs/provider audit records, and notify the approved stakeholders.
2. Stop public traffic at the edge if needed. Avoid stopping or deleting the
   database/storage service before preserving evidence and a recovery copy.
3. Identify the last known-good PostgreSQL backup/PITR point and matching S3
   document versions. Confirm integrity, encryption-key access and expected
   data loss window.
4. Rehearse restore in isolated staging. The DBA and incident lead approve
   whether roll-forward, point-in-time recovery, or full restore is appropriate.
5. Restore only with the provider-specific procedure, verify migrations,
   runtime grants/RLS, user login, organization isolation, attachments,
   traceability, notifications and audit records, then reopen traffic with
   customer approval.
6. Record timeline, impact, RPO/RTO achieved, missed alerts, data reconciliation
   and follow-up actions. Rotate exposed credentials/keys through the approved
   secret-management process.

## Deployment and rollback safeguards

- Keep a tested previous release reference and an up-to-date backup before
  migrations. Confirm the application/database compatibility window.
- Do not assume Alembic downgrade is supported. Prefer a forward repair unless
  an approved restore has been rehearsed.
- Never run `docker compose down -v`; never delete existing user data or volumes
  as a troubleshooting shortcut.
- Escalate missing monitoring, backup failures, certificate errors, ClamAV
  outage, repeated Celery failures or cross-tenant access anomalies immediately.
