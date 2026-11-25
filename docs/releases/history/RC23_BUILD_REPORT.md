# FactoryLink RC23 Build Report — local package hardening

**Version:** `1.0.0-rc.23`  
**Date:** 2026-11-03  
**Status:** Hardened local candidate. Not production-certified or approved for real factory data.

## Changes in RC23

- Reduced the backend Docker build to runtime dependencies only; moved `pytest` and `httpx` to `backend/requirements-dev.txt` for test/CI use.
- Removed unnecessary `apt-get`, `curl` and `build-essential` installation from the runtime image. The backend image installs pinned binary wheels only, avoiding unplanned native source builds.
- Added bounded pip retries/timeouts and configurable `PIP_INDEX_URL` so a corporate/approved package mirror can be selected without editing the Dockerfile.
- Changed Docker Compose start scripts to verify that the Docker Engine is running and use plain build progress so dependency failures are visible.
- Passed S3 storage settings through to the Docker Compose API container. Local mode remains the default; production should use private S3 and a least-privilege role.
- Moved old RC build reports and acceptance JSON files under `docs/releases/history/`; removed generated pytest cache from the package.
- Added a focused local troubleshooting guide and updated test-install/CI instructions.

## Verification performed in this environment

- Reproducible acceptance runner with backend regression tests intentionally skipped: **5 passed, 0 failed, 6 skipped**. Passed: Python compilation, fresh Alembic upgrade through `0007_quality_capa_serial_traceability`, first demo seed, repeat seed and live Uvicorn factory/supplier manufacturing workflow.
- RC22 test records included in the source: **130 backend tests passed** across the recorded test groups; 3 focused RC22 workflow tests are included in that total. These are the prior RC22 recorded results, not a full RC23 rerun.
- RC23 regression tests rerun: **59 passed** across six test files; **3 passed** for the focused RC22 core-workflow API cases.
- `python -m compileall -q app migrations tests`: passed.
- Compose, Render and GitHub Actions YAML parsed successfully; Compose exposes nine declared services.
- `bash -n` passed for startup, E2E, backup/restore and PostgreSQL acceptance shell scripts.
- `node --check scripts/load/k6-smoke.js`: passed.

## Not executed here

- Docker Compose image build/start; Docker/Podman is not installed in this environment.
- Dependency-backed Vite build and Playwright browser journeys; npm registry access is unavailable in this environment. A frontend `package-lock.json` is not included yet, so transitive npm dependencies are not fully lockfile-frozen.
- Full PostgreSQL 17 RLS/ACL/trigger/concurrency test, Redis/Celery live services, real ClamAV 1.5 signature warm-up/EICAR upload tests and live S3/IAM integration.
- Backup/restore drill, k6 load test, independent penetration/security review, staging deployment and factory customer acceptance.

## Release note

RC23 improves package layout, container dependency separation and diagnostics. It does not claim that the earlier user-reported `pip install` error has been reproduced: the user's Docker build output did not include the underlying pip resolver/network message. The new build output keeps that cause visible. If the failure is a package-index DNS/TLS/network problem, it must be corrected on the user's Docker/network environment or by setting an approved internal `PIP_INDEX_URL`.

This package is intended for local evaluation with fictional sample data. Do not treat it as certified, production-approved or validated against real factory infrastructure until the outstanding checks pass.
