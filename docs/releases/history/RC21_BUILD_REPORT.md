# FactoryLink RC21 Build Report — ClamAV feature-line refresh and verified acceptance

**Version:** `1.0.0-rc.21`  
**Date:** 2026-11-03  
**Status:** Local evaluation release candidate. Not production-ready, certified or approved for real factory data.

## RC21 changes

- Updated the official ClamAV scanner image from the 1.4 to the 1.5 feature line in both Docker Compose and `scanner/Dockerfile`. The deployment guide recommends feature-version tags rather than floating `latest`; see the [official ClamAV Docker image guidance](https://docs.clamav.net/manual/Installing/Docker.html).
- Updated release-integrity assertions, deployment instructions, README, changelog, project status and the final acceptance checklist.
- Kept the scanner private-only: TCP 3310 is not published to the host, and the backend waits for scanner health before starting.

## Verification performed

### Backend regression suite

Command (from `backend/`): `python -m pytest -q`  
Result: **127 passed in 28.11s**. This includes ClamAV INSTREAM/PING protocol tests using a local fake daemon; it does not prove a real ClamAV service/signature database works.

### Reproducible acceptance runner

Command: `python scripts/acceptance/run.py --skip-backend-tests --report /tmp/rc20-acceptance-final-verified.json`  
Result in this invocation: **5 passed, 0 failed, 6 skipped**. The backend suite was intentionally disabled inside the runner and was executed separately as described above. Combined release result: **6 passed, 0 failed, 5 outstanding infrastructure gates**.

Passed checks: Python compilation; fresh Alembic migration; first demo seed; repeatable second seed; and live Uvicorn factory/supplier workflow covering health, metrics, factory dashboard, supplier purchase-order visibility and denials, linked receipt (12/12 kg), production completion, failed quality inspection, quality hold and traceability.

### Additional source checks

- PyYAML parsed `docker-compose.yml`, `render.yaml` and `.github/workflows/ci.yml`.
- Compose declares nine services; ClamAV has no host-published port; backend depends on the scanner's healthy condition.
- `bash -n` passed for startup, database, backup and E2E shell scripts.
- `node --check scripts/load/k6-smoke.js` passed.
- `python -m compileall -q backend/app backend/migrations backend/tests` passed.

## Explicitly not executed

The following gates remain open because the required runtime tools, services or packages are unavailable in this environment:

- Docker Compose build/start, real ClamAV 1.5 signature warm-up, health checks, EICAR rejection, clean-file upload and scanner-outage upload test.
- PostgreSQL 17 RLS, grants, triggers and runtime-role acceptance; Redis and Celery service/task execution.
- Frontend dependency installation, lockfile generation, dependency-backed TypeScript/Vite production build and actual Playwright browser journeys. `frontend/node_modules` is absent and npm registry access failed.
- Real private S3 bucket/IAM integration and credential rotation.
- Real PostgreSQL backup/restore drill, k6 load run, independent security/penetration review, staging deployment and customer acceptance.

Tool availability check: Docker, Podman, PostgreSQL (`psql`/`postgres`/`pg_ctl`) and Redis (`redis-server`/`redis-cli`) are unavailable; frontend dependencies are not installed.

## Release decision

RC21 improves the malware-scanner image version and passes the local backend/live-API acceptance that can run on this host. It is **not production-ready**. Do not import real factory, supplier or customer data or expose the service publicly until all infrastructure-dependent checks above pass in a controlled staging environment, a real scanner EICAR/clean-upload test passes, an independent security review is complete, backups are restored successfully, and the factory owner approves go-live.
