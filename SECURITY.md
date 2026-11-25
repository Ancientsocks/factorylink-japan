# Security Policy

## Scope

This release is intended for local evaluation. Do not use it to store real production, supplier, employee or customer data until a deployment-specific security review is complete.

## Report a vulnerability

Do not publish exploitable details in a public issue. Contact the project maintainer through a private channel and include affected version, impact and reproducible steps. No public security response SLA is currently established.

## Current controls

- Passwords are salted and hashed using PBKDF2-HMAC-SHA256.
- Access tokens are short-lived; refresh tokens are random, stored as SHA-256 hashes and rotated on refresh.
- Each login has a refresh-token family. Reuse of a rotated ancestor revokes all active descendants in that family while preserving independent sessions for the same user.
- API endpoints validate roles and organisation ownership for implemented business operations.
- New workspace registration creates the first organisation-scoped account and assigns the initial role based on manufacturer/supplier type.
- Supplier access is limited to purchase orders and documents linked to their supplier organisation.
- CORS is configurable; security response headers are enabled.
- Public workspace registration is configurable; production startup refuses to run while public registration or demo seeding is enabled.
- Uploads enforce file extension allow-list and size limit, and use generated storage names.
- PostgreSQL and Redis are not published to host ports in the Compose configuration.

## Required before production

- Replace all secrets and demo passwords; use a secret manager.
- Terminate TLS at a trusted reverse proxy or managed platform.
- Apply request rate limiting and abuse protection to public workspace registration and login; add CAPTCHA/verification or an invite/approval gate before public exposure.
- Add MFA/SSO where required and a verified password-reset workflow with delivery through a trusted email provider.
- Use an administrator-approved onboarding process or verified invitation flow after setting `ALLOW_PUBLIC_REGISTRATION=false` in production.
- Execute and independently review the PostgreSQL RLS policies in migration `0004_postgresql_tenant_rls` against a real PostgreSQL instance, including negative tests for cross-tenant reads/writes and linked supplier operations.
- Review the intentionally unprotected-by-RLS identity tables (`organizations`, `users`, and `refresh_tokens`) and their authentication/registration code paths as part of the threat model.
- Uploads are size bounded (10 MiB), extension allow-listed, signature/content-checked, and stored under opaque random keys. Production requires private S3-compatible storage; the API never sets public ACLs and performs tenant/supplier authorization before streaming downloads. Downloads are `attachment`, `private, no-store` and `nosniff`.
- S3 baseline: Block Public Access on, Bucket owner enforced (ACLs disabled), versioning on, default SSE-S3/SSE-KMS encryption, and a dedicated API identity limited to `PutObject`/`GetObject`/`DeleteObject` on the one bucket's objects. Keep credentials only in the secret manager; use ECS/EC2 workload identity on AWS. Real bucket/IAM integration is not yet verified.
- Uploads are scanned by a private ClamAV `clamd` service using the INSTREAM protocol before any bytes are persisted. Production startup rejects disabled or unconfigured scanning; malware detections are rejected and scanner errors/timeouts fail closed. The readiness probe includes scanner PING when enabled. The clamd TCP protocol is unencrypted and unauthenticated, so never publish port 3310 or connect to it across an untrusted network; keep it on a private application network. Real ClamAV image/signature-database runtime, EICAR acceptance in the real container and scanner outage recovery still require Docker/staging verification.
- Configure database backups, restore drills, audit retention, log redaction and incident response.
- Conduct dependency, container, application and penetration testing.
- Have legal/privacy and industry requirements reviewed by qualified Japanese advisors. This software makes no certification or statutory-compliance claim.


## PostgreSQL row-level security

Migration `0004_postgresql_tenant_rls` enables and forces RLS on all organisation-owned operational tables. The current tenant is set transaction-locally from the verified JWT claim and re-applied at each new transaction. Supplier cross-tenant access is limited by explicit policies to linked supplier records, purchase orders, supplier-workflow updates, relationship notifications, and purchase-order attachments. Organisation, user, and refresh-token identity lookups are not covered by the operational RLS policies and continue to rely on authentication logic and application-level scoping. The Compose configuration creates a dedicated non-owner, non-superuser runtime database role for API and Celery processes; the one-shot migration service alone uses the database owner. Do not expose database credentials. Policies and grants are present in source but still require execution and negative/positive policy tests against a real PostgreSQL instance before production approval.


## Database runtime role

The Compose stack creates a separate non-owner application role with `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, and no schema ownership. The API and Celery use that runtime role; only the one-shot migration service uses the database owner. The bootstrap grants the runtime role only the initial access needed for migration-reviewed narrowing; migration `0004` revokes table-wide UPDATE/DELETE and grants UPDATE only on documented workflow columns. The runtime login must not have `BYPASSRLS`, schema ownership, DDL privileges, or membership in the owner role. `alembic_version` is read-only to the runtime account.


## Column-level runtime write privileges

Migration `0004` narrows the broad DML bootstrap grant. The runtime role cannot delete application rows; immutable audit, stock movement, inspection and traceability records cannot be updated. Updates are column-limited to the fields used by the application: user language, refresh-token revocation links, purchase-order workflow status/note, batch stock/status fields, production status/output/reservation fields, equipment status/downtime, maintenance status/downtime/notes, and notification read state. Review these grants whenever an API write workflow changes.


## Password reset and invitations

Password reset and invitation tokens are generated with a cryptographically secure random source; only SHA-256 token digests are stored. Tokens are purpose-bound, expire, and are single-use. Password reset invalidates every active refresh-token family for that user. Invitation-created users cannot log in until redemption. Do not enable `EXPOSE_AUTH_ACTION_LINKS` outside isolated development. Configure SMTP credentials through environment secrets, never source control.

Password reset revokes refresh-token sessions immediately. Existing short-lived access JWTs are not centrally revoked and remain valid until their configured expiry (20 minutes by default); keep access-token TTL short and consider a token-version/revocation cache before deployments that require immediate access-token invalidation.


## Runtime-role bootstrap is restart-safe

The `db-bootstrap` service runs on every Compose invocation. It first revokes broad table-level `UPDATE` and `DELETE` from the runtime role, then conditionally reapplies the reviewed column-level updates needed by the application (including session rotation, password reset/invitation redemption, purchase-order status, inventory quantities/reservations, production progress, maintenance and notification read state). It revokes Alembic history writes after the global read/insert grant. Future tables default to SELECT/INSERT only. Run `scripts/db/verify-runtime-role.sql` and `scripts/db/verify-rls.sql` on PostgreSQL 17 before production; SQLite cannot prove the database ACL/RLS boundary.


## Supplier-visible receipt progress

Supplier accounts are not granted SELECT access to factory `material_batches` or `inventory_movements`. The cumulative receipt quantity is instead stored on the linked purchase-order record and advanced atomically with a linked goods receipt while the factory PO row is locked. Migration `0006_supplier_receipt_progress` backfills historical totals from receipt movement records. A PostgreSQL `BEFORE UPDATE OF received_quantity` trigger verifies that `app.current_organization_id` equals the PO-owning factory, so supplier sessions cannot forge receipt totals even though the shared runtime DB role has a column-level UPDATE grant for the factory workflow. The supplier PO RLS policy additionally verifies the supplier directory record and PO have the same manufacturer owner. Execute `verify-rls.sql` and the live API smoke in `postgres-acceptance.sh` on PostgreSQL 17 to validate these controls.


## RC15 production transport requirements

Production startup now rejects: non-HS256 JWT configuration; PostgreSQL URLs that do not use `postgresql+psycopg` with TLS `sslmode=require`, `verify-ca` or `verify-full`; wildcard or non-HTTPS CORS origins; SMTP without STARTTLS; and partial SMTP username/password configuration. The React application receives a restrictive Content Security Policy (`default-src 'self'`, no objects, no frames, same-origin scripts/connections). FastAPI Swagger docs retain their dedicated route because its UI initializer uses inline script code; do not expose interactive API docs publicly in a production environment without access controls. The reverse proxy must overwrite the incoming `X-Forwarded-Proto` header from the actual TLS connection before Nginx uses it to emit HSTS.


## First production administrator bootstrap

When public workspace registration is disabled for production, the initial manufacturer tenant is created only by the operator CLI (`python -m app.render_deploy bootstrap-admin`) after database migrations. The command accepts no default credentials, prompts for a unique 14+ character password without echoing it, creates the first tenant and `ORG_ADMIN` in one transaction, and writes an audit event. It refuses to run if any organisation or user already exists. There is no public HTTP bootstrap route. Subsequent users must be created through the invitation workflow.

## Render migration and runtime credentials

Render deployment uses a saved owner connection URL only during pre-deploy migrations and a separate Render-managed default credential for API/worker/scheduler traffic. The runtime helper checks role superuser, CREATEDB, CREATEROLE, BYPASSRLS and role-membership flags before granting only reviewed application permissions. A failed check blocks deployment. Keep the original owner URL in a secret manager; never set it as `DATABASE_URL` for long-running services.
