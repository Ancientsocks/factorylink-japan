# FactoryLink release review — 2026-11-05

## Included in this source release

- Render API, worker and scheduler now remove `OWNER_DATABASE_URL`,
  `RUNTIME_DATABASE_URL` and the fallback runtime password from the inherited
  environment after deriving the restricted `DATABASE_URL`.
- Alembic receives only the owner URL under its one-shot `DATABASE_URL`; the
  extra owner/runtime connection variables and fallback password are removed
  from the child environment.
- The Render Blueprint enables fail-closed Redis-backed rate limiting and
  provisions a private ClamAV service with a persistent signature disk.
- The API's malware-scanner host is wired from that private service rather than
  requiring a manually copied hostname.
- Production login fields are blank, demo accounts are rendered only in Vite
  development mode, the fixed demo password is removed from the frontend, and
  public self-registration is development-only unless a production build opts
  in explicitly with `VITE_FACTORYLINK_PUBLIC_REGISTRATION=true`.
- Regression checks cover the owner-secret cleanup, mandatory Render settings,
  scanner service reference and frontend production credential removal.
- The Render deployment guide now matches the two-Blueprint first-deploy order
  and lists the external backup, monitoring, email and Japan-residency gates
  separately.

## Static verification performed for this package

- Python source compilation: passed.
- Focused backend release-integrity and Render deployment tests: **51 passed**.
- TypeScript project check (`tsc -b`): passed using the dependency files from the
  uploaded archive.
- YAML parsing for `render.yaml`, `render-database.yaml` and all three Compose
  files: passed.
- Render Blueprint service plans, Key Value settings, database settings, disk
  settings and service-reference syntax were checked against the current
  official Render Blueprint reference (2026-11-05).
- The full backend suite was not re-run because Redis, Celery and Psycopg
  dependencies were absent and package-registry access was unavailable. The
  uploaded Windows virtual environment is not portable to this Linux runtime.
- Frontend Vitest/build were not re-run: the uploaded `node_modules` contains
  Windows-specific optional native packages; the package-registry network was
  unavailable for a clean Linux `npm ci`. The TypeScript check did pass.
- No Render Blueprint sync, public deployment, S3/ClamAV/SMTP provider test,
  or Japan-based data-residency approval was performed.

## Go-live still requires

1. Sync `render-database.yaml` first, save the owner URL, create the managed
   `factorylink_app` default credential, then validate/sync the application
   `render.yaml` in the customer's Render workspace. Review all paid-service
   prices and plan selections.
2. Provision private S3 with versioning/encryption and verify clean, infected
   and scanner-unavailable upload cases.
3. Configure SMTP and test invitation and password-reset delivery.
4. Configure encrypted off-site database/document backups, retention, provider
   PITR, and complete a provider-side restore drill.
5. Configure durable monitoring and alert delivery, including API, worker,
   scheduler, queue, scanner, storage, backup and database signals.
6. Review Japan/Singapore cross-border data processing with the customer.
7. Complete Japanese factory acceptance, access-control/RLS tests, and a
   customer-approved production capacity test.

This artifact is a hardened release candidate, not a declaration of
certification, compliance, or production approval.


### First-deploy database sequencing correction

The Render PostgreSQL instance is now provisioned separately by
`render-database.yaml`. The operator saves the initial owner URL, creates the
managed `factorylink_app` default credential, and only then syncs the
application-services `render.yaml`. This prevents the initial migration from
starting with the database owner still configured as the runtime URL. The app
Blueprint references the existing database and does not manage it a second time.
