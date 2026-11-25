# FactoryLink

**Manufacturing Operations & Supplier Collaboration Platform**  
**Local package:** Japan Local RC24 · **Application version:** `1.0.0-rc.24`

FactoryLink is a Japan-oriented web application for manufacturers and their suppliers. It brings procurement, inventory, production, quality, lot/serial traceability, maintenance, documents, notifications and operational reporting into one workspace. The interface supports English and Japanese, with `Asia/Tokyo` as the default display timezone and JPY as the default currency.

> **Release status:** This is a hardened local evaluation candidate, not a certified or production-approved system. Use fictional demo data until Docker, browser, PostgreSQL, Redis/Celery, ClamAV, storage, recovery, security and factory acceptance checks have passed.

## Verification status — 2026-11-25

- Backend regression suite: **207 passed** (Python 3.12, FastAPI 0.165.0 / Starlette 1.10.0), including 15 edit/delete, 12 email-verification, 9 Google sign-in and 7 email-delivery regression tests.
- PostgreSQL 17.11: `alembic upgrade head` reaches `0014` on an empty database both with and without the restricted runtime role; `scripts/db/verify-runtime-role.sql` reports a least-privilege pass; running the API as `factorylink_app` allowed supplier create/patch/delete and equipment patch against a real server.
- Docker Compose: both compose files validate, images build from this tree, the full stack (PostgreSQL, Redis, ClamAV, migrate, backend, worker, scheduler, frontend) starts healthy, `/health/ready` reports database, Redis and scanner ok, and `scripts/postgres-api-smoke.py` passed against the stack.
- Account security: registration and forgotten-password recovery require a six-digit code emailed to the address before a password is set; codes are hashed, expire in ten minutes, allow five attempts and are rate limited. Codes are delivered by SMTP or the Resend HTTPS API (HTML + plain text), and the API reports when no channel is configured instead of claiming a send.
- Google sign-in and sign-up are supported when `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are set: existing accounts sign in, new Google users confirm their workspace details, and the button stays hidden until the server reports the provider enabled. The live Google round-trip was not exercised (no client ID in this environment); the server-side hand-off is covered by tests and a simulated browser hand-off.
- Frontend unit suite: **8 passed**; production TypeScript/Vite build passed (1,580 modules).
- Dependency audits: `pip-audit -r backend/requirements.txt` and `npm audit --audit-level=high` report **no known vulnerabilities**.
- Local acceptance runner: **5 passed, 0 failed, 6 skipped** (fresh Alembic migration, idempotent seed, live API manufacturing workflow).
- **Not run in this pass:** Playwright browser journeys, Render deployment, private S3, delivery to a real customer inbox (no SMTP/Resend credentials here), a real Google consent round-trip (no client ID here), external monitoring and backup/PITR drills. These remain release gates, not claims.

## Core business workflow

1. A manufacturer creates a purchase order and shares it with a linked supplier.
2. The supplier confirms the order, updates delivery status and shares permitted documents.
3. The factory records partial/final goods receipts. Each receipt creates lot/batch inventory and immutable stock movements.
4. Production orders reserve eligible stock using FIFO, record progress and consume reserved materials on completion.
5. Accepted completed units receive unique finished-product serial numbers linked to the source material lots. Rejected units are not serialised.
6. Quality inspections use reusable templates and pass/fail or numeric tolerance criteria. A failure creates a quality hold and a CAPA case; release is explicit and evidence-gated.
7. Lot/serial traceability shows supplier, PO, receipts, inventory movements, production, inspection, CAPA and shipment events. QR codes can be downloaded; camera scanning is available in supported browsers with manual search as fallback.
8. Equipment maintenance tracks preventive and unplanned work and reports downtime. Dashboards, notifications, audit logs and CSV/XLSX reports use tenant-scoped application data.

## Main modules

- Multi-tenant manufacturer/supplier workspaces, authentication, refresh-token rotation and role-based access.
- Supplier registry, purchase orders, supplier portal, partial delivery, goods receipt and document sharing.
- Edit and delete for suppliers, purchase orders, production orders, equipment, maintenance tasks, quality templates, users and shared documents. The server only allows edits while a record is still mutable and refuses deletes that would orphan stock, quality or maintenance history; accounts are deactivated rather than erased and quality templates are retired, so audit trails remain intact.
- Materials, batches/lots, FIFO reservations, consumption, reason-coded adjustments and stock movement ledger.
- Production orders, progress, completed/rejected quantities and finished-product serialisation.
- Quality templates, inspections, defects, CAPA lifecycle, batch holds and controlled release.
- Forward lot genealogy, backward serial genealogy, QR generation, camera/manual lookup and shipment records.
- Equipment, preventive maintenance, breakdown/downtime records and maintenance analytics.
- Real-data dashboards, notifications, audit history and CSV/XLSX reports.
- English/Japanese UI, Japanese UTF-8 data handling, Asia/Tokyo display and JPY formatting.

## Technology

- **Frontend:** React 19, TypeScript, Vite, Nginx.
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic.
- **Data/services:** PostgreSQL 17, Redis 7, Celery worker and scheduler.
- **Documents/security:** local persistent volume for local evaluation; private S3-compatible storage for production; private ClamAV scanning in Compose.
- **Tests:** Pytest, HTTPX, Playwright and scripted acceptance checks.
- **Deployment foundations:** Docker Compose, a single Render Blueprint and GitHub Actions.

## Repository structure

```text
FactoryLink/
├── backend/                 # FastAPI app, SQLAlchemy models, migrations and tests
│   ├── app/                  # API, business rules, storage, scanner and background tasks
│   ├── migrations/           # Alembic migration history
│   ├── tests/                # Backend tests
│   ├── requirements.txt      # Runtime dependencies (Docker/Render)
│   └── requirements-dev.txt  # Runtime + backend test dependencies
├── frontend/                # React/TypeScript app and Nginx configuration
├── scanner/                 # ClamAV image definition
├── e2e/                     # Playwright browser journeys
├── scripts/                 # Startup, acceptance, DB, backup/restore and load tools
├── docs/                    # Architecture, workflow, decisions and release evidence
├── docker-compose.yml       # Local multi-container environment
├── render.yaml              # Single Render Blueprint: database + application services
├── .env.example             # Local environment template; never put real secrets here
└── README.md
```

Historical RC build evidence is kept under `docs/releases/history/`. Current RC24 evidence is under `docs/releases/`.

## Requirements for local run

- Windows 10/11 with Docker Desktop, or Docker Engine + Compose on macOS/Linux.
- Docker Desktop configured for **Linux containers** and running.
- Internet access for the first image/package download.
- Allocate about 4 GiB RAM or more to Docker Desktop for ClamAV signature loading; more memory improves startup headroom.

## Quick start — Windows PowerShell

1. Extract the ZIP into a normal writable folder.
2. Open Docker Desktop and wait for **Engine running**.
3. Open PowerShell in the extracted `FactoryLink` directory.
4. Run:

   ```powershell
   .\scripts\start.ps1
   ```

5. The script creates `.env` from `.env.example` for local evaluation, checks Docker Engine, then builds and starts the services. First start may take several minutes while images, Python/npm packages and ClamAV signatures are downloaded.
6. Open [http://localhost:8080](http://localhost:8080). API docs are at [http://localhost:8080/docs](http://localhost:8080/docs).

### macOS / Linux

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

Open [http://localhost:8080](http://localhost:8080).

## Local demo accounts

All users and companies are fictional. The listed account and password are for **local development/demo seeding only**; demo seeding and these credentials are disabled in the production Render configuration. Never reuse this password for a real user.

| Role | Email |
|---|---|
| Factory administrator | `admin@factorylink.jp` |
| Production manager | `production@factorylink.jp` |
| Warehouse manager | `warehouse@factorylink.jp` |
| Quality inspector | `quality@factorylink.jp` |
| Maintenance manager | `maintenance@factorylink.jp` |
| Operator | `operator@factorylink.jp` |
| Supplier user | `supplier@osaka-parts.jp` |
| Separate-tenant administrator | `admin@tokyo-industrial.jp` |

Do not use these accounts or passwords in shared, staging or production deployments. Rotate all secrets and demo credentials before exposing any environment.

## Useful commands

```powershell
# Inspect service status and logs
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend

# Stop services but preserve local data volumes
docker compose down

# Rebuild and start with full build output
docker compose --progress plain up --build -d
```

`docker compose down -v` deletes the PostgreSQL database, Redis persistence, uploaded files and ClamAV signatures. It is destructive; export data first.

## Development and tests

Backend tests use isolated SQLite fixtures. From the project root:

```powershell
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app migrations tests
```

Frontend development/build:

```powershell
cd frontend
npm install --no-audit --no-fund
npm run build
```

Playwright journeys:

```powershell
cd ..
.\scripts\e2e\run.ps1
```

The acceptance runner reports checks that need Docker/PostgreSQL/Redis/browser prerequisites as **SKIP**, not PASS. See [TESTING.md](TESTING.md) and [FINAL_ACCEPTANCE_CHECKLIST.md](FINAL_ACCEPTANCE_CHECKLIST.md).

## Configuration notes

- `.env` is created automatically from `.env.example` for local evaluation. Review it before starting.
- `PIP_INDEX_URL` may be set to an approved internal PyPI mirror where direct PyPI access is restricted. Never disable TLS verification or use an untrusted package index.
- Local Compose defaults to `STORAGE_PROVIDER=local` with a persistent named upload volume. Production must use a private S3 bucket and least-privilege IAM credentials/role.
- Compose keeps PostgreSQL, Redis and ClamAV private to the application network; ClamAV TCP 3310 is not published to the host.
- Production startup requires secure settings, private object storage, malware scanning, SMTP, disabled public registration/demo seeding and valid HTTPS origins. Review [DEPLOYMENT.md](DEPLOYMENT.md) and [SECURITY.md](SECURITY.md).

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Database design](DATABASE_DESIGN.md)
- [API documentation](API_DOCUMENTATION.md)
- [Deployment](DEPLOYMENT.md)
- [Security](SECURITY.md)
- [Testing](TESTING.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Windows setup](WINDOWS_SETUP.md)
- [User guide](USER_GUIDE.md)
- [Release notes](RELEASE_NOTES.md)
- [Project status](PROJECT_STATUS.md)
- [RC24 build report](docs/releases/RC24_BUILD_REPORT.md)

## Known limitations before production

- Docker Compose startup, PostgreSQL migrations and least-privilege grants have been verified; automated browser journeys (Playwright) have not been run in this pass.
- Frontend dependencies are lockfile-pinned (`frontend/package-lock.json`, lockfileVersion 3) and installed with `npm ci`, so resolution is reproducible; direct versions remain pinned in `frontend/package.json`.
- PostgreSQL RLS/ACL/triggers/concurrency and Redis/Celery must be verified against live services; SQLite tests do not prove PostgreSQL security behaviour.
- Real ClamAV signature warm-up, clean/EICAR/outage upload behaviour and S3/IAM access must be tested against actual services.
- SMTP delivery, backups/restores, load, security review, staging and factory/customer acceptance remain environment-specific deployment activities.
- Camera scanning depends on browser `BarcodeDetector` support; manual identifier search is the fallback.
- FactoryLink makes no claim of Japanese regulatory certification or customer approval.
