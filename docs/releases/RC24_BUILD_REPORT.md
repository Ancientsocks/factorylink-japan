# FactoryLink RC24 Build Report — consolidated local release packaging

**Version:** `1.0.0-rc.24`  
**Date:** 2026-11-03  
**Status:** Core-complete local evaluation candidate. Not certified, production-approved or proven against real factory infrastructure.

## Changes

- Preserved the RC22 application features: organisation-scoped factory/supplier workspaces, procurement, inventory ledger, FIFO reservation, production, reusable quality templates, CAPA lifecycle, quality holds/releases, finished-product serials, forward/backward genealogy, QR generation, shipment tracking, maintenance classification, reports, notifications, audit history and English/Japanese UI.
- Kept backend runtime dependencies separate from `backend/requirements-dev.txt`.
- Backend Docker build installs pinned runtime dependencies as binary wheels with bounded pip retries/timeouts and supports an optional `PIP_INDEX_URL` build argument. The index URL is not written into the final runtime image environment.
- Docker startup scripts verify that the Docker Engine is reachable and use plain Compose build progress so pip/npm resolver errors remain visible.
- Frontend container install suppresses `npm audit` and funding calls during image build.
- Archived old RC build reports and test records under `docs/releases/history/` and kept the current report under `docs/releases/`.
- Added `WINDOWS_SETUP.md`, `USER_GUIDE.md`, `RELEASE_NOTES.md` and updated the current acceptance checklist and obsolete workflow/RBAC documentation.

## Verification executed for this packaging pass

- Reproducible local acceptance runner (`python scripts/acceptance/run.py --skip-backend-tests --report /tmp/factorylink-rc23-acceptance.json`): **5 passed, 0 failed, 6 skipped**. The backend regression suite was intentionally disabled by the flag. Passed checks: Python compilation, fresh SQLite Alembic migration to `0007_quality_capa_serial_traceability`, first demo seed, idempotent repeat seed, and a live Uvicorn factory/supplier manufacturing workflow.
- RC24 backend regression groups rerun in this packaging pass: **66 passed** across release-integrity/admin-bootstrap/Render-deploy tests (44), mailer/malware-scanner/object-storage tests (19), and the three focused core-workflow API tests (3).
- Prior RC22 grouped backend result: **130 passed** across the recorded full API/supporting groups. This is inherited RC22 evidence, not a full RC24 rerun of all 130 tests.
- Python syntax compilation, Compose/Render/CI YAML parsing, shell script syntax checks and k6 JavaScript syntax checks are recorded as passed in RC23 evidence.

## Not run / not verified in this environment

- Docker image build and full Docker Compose runtime: Docker/Podman is not installed in the packaging environment.
- Frontend `npm install`, dependency-backed TypeScript/Vite production build and Playwright browser journeys: npm registry access is unavailable here. A `frontend/package-lock.json` could not be generated. Direct frontend versions are pinned in `frontend/package.json`, but transitive npm dependencies are not fully lockfile-frozen.
- Real PostgreSQL 17 RLS/ACL/triggers/concurrency and runtime-role acceptance; SQLite migration/tests do not prove PostgreSQL policy behaviour.
- Real Redis/Celery worker and scheduler service execution.
- Real ClamAV 1.5 database warm-up, clean/EICAR upload and scanner-outage tests.
- Real S3/IAM integration, backup/restore drill, k6 load test, independent penetration/security review, staging deployment and factory/customer acceptance.

## Previously reported Docker pip-install failure

The reported `ResolutionImpossible` was caused by `redis==6.4.0` conflicting with the Redis range required by `celery[redis]==5.5.3` through Kombu. The backend runtime pin is now `redis==5.2.1`; Celery remains at 5.5.3 and the Redis server image remains `redis:7-alpine`. A pip resolver dry run of the complete backend runtime requirements succeeded after this change.

The Docker Compose configuration and image builds were not executed during this verification, so the Python 3.12 image build and complete container runtime remain unverified. If a subsequent build fails, retain the full error output so any separate build or package-index issue can be diagnosed.

## Release decision

RC24 is intended as one consolidated local application package for the user to run on Windows with Docker Desktop and fictional demo data. It is **not a production-certified or production-approved release**. Do not import real factory/customer data or expose the application publicly until every applicable service, security, recovery, Japanese-language, business-process and factory-owner acceptance gate is completed.
