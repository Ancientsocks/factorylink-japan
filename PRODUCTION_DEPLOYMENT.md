# Production deployment

This is an operator procedure for a **new, separately provisioned deployment**.
It does not deploy the application, alter the existing FactoryLink Compose
stack, or authorize use of real production data. Validate every step in an
isolated staging environment first.

## Topology

`docker-compose.production.yml` runs the backend API, migration runner, Celery
worker/scheduler, Redis, ClamAV, unprivileged Nginx frontend, Caddy TLS edge,
and a non-root scheduled backup container. Only Caddy publishes ports 80/443
TCP and 443 UDP. PostgreSQL, SMTP and private S3 are external services and are
not created or modified by this Compose file. The backend runs as the non-root
user in `backend/Dockerfile`; the frontend runtime uses nginx-unprivileged.
Compose volumes persist Redis, ClamAV, uploads, and Caddy state.

## Customer/provider prerequisites

Before deploying, provision and record:

1. A supported Linux Docker host and Docker Compose v2. Restrict SSH/admin access,
   firewall inbound traffic to the intended edge ports, and allow outbound
   connections only as required.
2. A company-controlled DNS name whose A/AAAA records point to the host. Ports
   80 and 443 must be reachable for Caddy/ACME validation. Provide a monitored
   operations email for ACME notices.
3. PostgreSQL 17 (or a compatibility-tested supported version) reachable from
   the host/network with TLS certificate validation. Create a migration-owner
   account and database. Do not use the owner account as the API runtime role.
4. A private S3-compatible bucket in the company-approved region. Enable
   block-public-access, encryption, versioning, access logging as appropriate,
   and lifecycle/replication based on the approved recovery policy. Use a
   workload IAM role where possible; otherwise use a narrowly scoped access
   key. Validate that the API can read/write/delete only the intended objects.
5. A company SMTP service with STARTTLS and a verified sender. Set SPF, DKIM,
   and DMARC as appropriate; verify reset and invitation messages in staging.
6. Secret-management ownership for database URLs, runtime password, JWT secret,
   Redis password, SMTP password, AWS credentials (if any), and age backup keys.
   The example file is documentation only and contains placeholders.
   Also supply a PostgreSQL CA file and a protected shell environment file for
   the scheduled backup container. Its database backup URL must be a libpq
   `postgresql://` URL with certificate verification, and its S3 source and
   backup buckets must be separate.
7. ClamAV network isolation and resource allocation. Its unauthenticated TCP
   service must remain private to the application network.
8. A decision on Japanese data residency, cross-border processing, retention,
   privacy notices, customer contracts, and subprocessors. The existing Render
   blueprint uses Singapore for app/DB services; this is not a Japan-residency
   guarantee.

## Configure and validate

1. Obtain the reviewed release source and record its commit/version. Before
   starting staging, verify Docker Engine connectivity and inventory current
   containers, images, Compose projects, and volumes using read-only commands.
   Identify the development database and its volumes; do not stop, delete,
   reset, or modify them. If Docker cannot connect, stop here: do not attempt
   staging startup or infer that any image/database revision is current.

   **Staging verification (2026-11-05):** Docker 29.8.1 / Docker Desktop
   4.93.0 / Compose 5.5.1 were reachable. Read-only inspection found the
   existing `factorylink` development project, its `factorylink_postgres_data`,
   `factorylink_redis_data`, `factorylink_factorylink_uploads`, and
   `factorylink_clamav_database` volumes, and a development database containing
   3 organizations and 8 users at revision `0009_finished_product_quality`.
   The existing backend container was not changed; `alembic current` in it
   fails because its image cannot locate revision `0009_finished_product_quality`.

   Isolated project `factorylink-staging-20261105-0108` was created with
   separate Compose-scoped PostgreSQL, Redis, and uploads volumes. The
   production-tagged backend image
   `sha256:9f44e23912fc571fa53a99a9d8fc20bf224366cf209bc749241ec312943fe8d4`
   and frontend image
   `sha256:a35bac9dc69ee1d78fb944bdbcb62d4911c852aac2fb49a41f0452b5dfee78cf`
   ran in staging; Alembic current/head both reported
   `0011_inventory_reconciliation`. Readiness returned HTTP 200 with database
   and Redis `ok`. PostgreSQL/RLS, Redis, migration recovery, workflow, browser,
   local backup/restore, load, and Celery evidence is recorded in
   [TESTING.md](./TESTING.md). The staging image/schema mismatch is resolved
   for that isolated environment. The existing development container remains
   stale by design; do not treat staging verification as a deployment or
   replace the development image/database as part of this procedure.

   For any later validation or promotion, use a fresh unique project name
   (never the default development or production project):

   ```sh
   docker compose -p factorylink-staging-20261105 -f docker-compose.staging.yml config --quiet
   docker compose --env-file .env.production.example -f docker-compose.production.yml build backend frontend
   docker image inspect factorylink-production-backend:latest factorylink-production-frontend:latest
   docker compose -p factorylink-staging-20261105 -f docker-compose.staging.yml up -d
   docker compose -p factorylink-staging-20261105 -f docker-compose.staging.yml ps
   docker compose -p factorylink-staging-20261105 -f docker-compose.staging.yml run --rm backend alembic current
   curl --fail --show-error http://127.0.0.1:18080/health/ready
   ```

   Compose scopes the staging database, Redis, and uploads volumes to the
   unique project name. PostgreSQL, Redis, and backend remain on the internal
   network; only the frontend joins a separate project-scoped ingress bridge,
   with its host port bound to loopback. Confirm the
   migration service used the intended image ID before evaluating results.
   Do not use `docker compose down -v`; do not reuse or prune any development
   resources.
   The staging stack uses fictional data only; seed it only when needed:

   ```sh
   docker compose -p factorylink-staging-20261105 --profile acceptance -f docker-compose.staging.yml run --rm seed
   FACTORYLINK_BASE_URL=http://127.0.0.1:18080 python scripts/db/postgres-api-smoke.py
   ```

   Run the PostgreSQL API workflow against the staging frontend/API endpoint
   and confirm procurement → receipt → inventory → manufacturing → finished
   product shipment/traceability. Run the frontend browser journey and inspect
   `/health/ready`. Keep this project isolated; stop it with:

   ```sh
   docker compose -p factorylink-staging-20261105 -f docker-compose.staging.yml stop
   ```

   Do not use `down -v` or reuse the project name for development.
2. Copy `.env.production.example` to `.env.production`; replace every
   placeholder. Restrict access to the file (`chmod 600` on Linux) or inject
   values from an approved secret manager. Do not commit the filled file.
   Replace `BACKUP_ENV_FILE` and `BACKUP_CA_FILE` with the actual protected
   deployment files; the checked-in examples are intentionally unusable
   placeholders. Set `BACKUP_CRON_SCHEDULE` to the approved schedule.
3. Set `PG_ADMIN_URL` to a TLS-verified PostgreSQL URL accepted by `psql`;
   set `MIGRATION_DATABASE_URL` and `RUNTIME_DATABASE_URL` to
   `postgresql+psycopg` URLs with `sslmode=verify-full` and an available trusted
   CA chain. URL-encode special characters in credentials. Configure the
   runtime role name/password and the migration owner role consistently.
4. Generate unique secrets. Use at least 32 random bytes for `JWT_SECRET_KEY`;
   use URL-safe hexadecimal for `REDIS_PASSWORD`. Keep the age encryption
   recipient public key in the backup scheduler configuration and the private
   identity separate and access-controlled.
5. Review the rendered config without printing secrets into shared logs:

   ```sh
   docker compose --env-file .env.production -f docker-compose.production.yml config --quiet
   ```

6. Apply in the isolated staging environment:

   ```sh
   docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
   docker compose --env-file .env.production -f docker-compose.production.yml ps
   ```

   This provisions/rotates the restricted PostgreSQL runtime role, runs Alembic
   to `head`, then starts dependencies and application services. It does not
   seed demo data or enable public registration. Review logs from each service
   before any user access.
   For a new, empty deployment only, create its first factory administrator
   interactively after the migration succeeds:

   ```sh
   docker compose --env-file .env.production -f docker-compose.production.yml run --rm -it backend python -m app.admin_bootstrap
   ```

   Confirm the intended database is the new deployment before entering
   credentials. The command refuses to run if any organization or user already
   exists. Do not run it against an existing customer database; use its existing
   administrator and invitation flow instead. The password is prompted without
   echo and must not be placed in command arguments, shell history, or logs.
7. Verify `https://<FRONTEND_DOMAIN>/health/ready`, the certificate chain,
   login, password recovery, invitation flow, English/Japanese switching,
   uploads/scanning/downloads, manufacturing acceptance, notifications,
   tenant isolation, and background tasks. `/docs`, `/redoc`, and
   `/openapi.json` must not be exposed in production.
8. Run PostgreSQL RLS/runtime-role acceptance and the bounded synthetic load
   test using an isolated staging account and disposable tenant. The load test
   creates manufacturing and inventory records; never point it at production.
   The PostgreSQL acceptance runner checks every
   organization-owned table for forced RLS, real Redis throttling, concurrent
   inventory updates, and migration failure/recovery using uniquely named
   disposable databases. Run it only against a disposable PostgreSQL service;
   it does not target or clean the application database. Run
   `scripts/load-test/manufacturing_transactions.py` against the dedicated
   staging tenant; it writes synthetic receipt records and must not run against
   production. Collect API latency/errors plus host, PostgreSQL, and Redis
   resource metrics. Complete the full backup and restore drill before
   approving production.
9. Record image/source version, Alembic head, provider configuration, test
   evidence, operators, and customer acceptance in the release record.

## Upgrades and rollback

- Back up PostgreSQL and S3 documents according to the runbook and verify the
  backup before a migration. Schedule a maintenance window when the migration
  or deployment may affect active manufacturing operations.
- Review every migration for locks, table rewrites, constraints and
  backward-compatibility. Run it on a recent isolated copy first. Do not assume
  a database downgrade is safe.
- Deploy the reviewed source and run the production Compose command above.
  Check migration output, service health, error logs, login and a defined
  read-only/workflow smoke test before reopening traffic.
- Prefer a forward fix when schema changes have committed. For a failed
  release, stop edge traffic, keep a copy of current database/S3 state, and
  follow a tested provider-specific restore/roll-forward decision. The legacy
  `scripts/backup/restore.sh` targets the development Compose database and is
  **not** a production restore tool.
- Never run `docker compose down -v`. Do not remove persistent volumes as a
  rollback method. Do not restore over a live database without explicit
  incident authorization, a verified rollback copy and a documented maintenance
  window.

## Not included / customer-specific

This repository cannot supply DNS, cloud credentials, AWS account policies,
database certificates, SMTP credentials, customer-managed keys, a selected
Japanese hosting region, external monitoring/alerting, support staffing,
privacy/legal approval, or a customer-specific RPO/RTO. Those are deployment
gates, not presumed controls.
