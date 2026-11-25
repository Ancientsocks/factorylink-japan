# FactoryLink RC20 Build Report — Malware scanning before document persistence

**Version:** `1.0.0-rc.20`  
**Date:** 2026-11-03  
**Status:** Local evaluation candidate. Not production-ready, certified, or approved for real factory data.

## RC20 implementation

- Added a bounded ClamAV `clamd` INSTREAM client that streams file bytes in 1 MiB chunks and accepts only a clean `stream: OK` reply.
- Added explicit malware-detected and scanner-unavailable exception paths.
- Document uploads now run malware scanning after size/extension/signature checks and before saving to local or S3-compatible storage. A detection returns HTTP 422; scanner outage, timeout or malformed response returns HTTP 503. No attachment row or stored object is created in either case.
- Production startup rejects malware scanning disabled or an absent/invalid scanner endpoint.
- Readiness checks include ClamAV PING whenever scanning is enabled.
- Added a private `clamav/clamav:1.4` Compose service with a persistent signature database volume and health check. The API waits for scanner health; TCP 3310 is not published to the host.
- Added `scanner/Dockerfile` and deployment guidance for a private scanner in Render/AWS environments.
- Added tests for clean scan, detected signature, invalid/error response, connection failure, PING, production configuration, upload rejection and non-persistence.

## Verification performed

### Backend suite

Command: `cd backend && python -m pytest -q`  
Result: **125 passed**.

### Reproducible acceptance runner

Command: `python scripts/acceptance/run.py --skip-backend-tests --report /tmp/rc20-acceptance-retry.json`  
Result: **5 passed, 0 failed, 6 skipped** in that invocation. The backend test suite was run separately and passed 125/125. The downloadable combined result records **6 passed, 0 failed, 5 skipped** after adding that separately executed backend suite.

Passed acceptance checks: Python compile, fresh Alembic migration, first demo seed, repeatable demo seed and live Uvicorn factory/supplier full workflow (PO, supplier confirmation/dispatch, receipt, production completion, failed inspection, quality hold and traceability).

### Additional source checks

- ClamAV INSTREAM/PING protocol exercised against a local fake clamd TCP server, including clean, malware, invalid response and unavailable cases. This is protocol-unit testing, not a real ClamAV daemon/signature database integration test.
- Compose and Render YAML parsed with PyYAML; nine Compose services and no host-published ClamAV port verified by source assertions.
- Shell/Python syntax and release-integrity checks are covered by the passing backend suite and compile command.

## Explicitly not executed

- Docker Compose image build/start, real ClamAV warm-up/signature update, health and EICAR test; Docker is not installed on this host.
- Real PostgreSQL 17 RLS, grants, triggers, Redis and Celery runtime acceptance; PostgreSQL/Redis tools/services are not installed here.
- Dependency-backed frontend Vite production build and Playwright browser journeys; frontend dependencies are not installed and npm registry access is unavailable in this execution.
- Real S3 bucket/IAM integration, Render/AWS deployment, backup/restore drill, load test, malware false-positive handling review and independent penetration/security review.

## Deployment considerations

- Local Docker Compose now starts nine services. The ClamAV image may take several minutes to warm/load signatures on first start and needs at least 4 GiB RAM according to the official ClamAV Docker guidance. Persist `/var/lib/clamav` to avoid repeatedly downloading the signature database.
- ClamAV TCP is unauthenticated and unencrypted. Do not publish port 3310; permit API-to-scanner traffic only on a private network.
- Production must set `MALWARE_SCAN_ENABLED=true` and configure a private `MALWARE_SCANNER_HOST`. The Render Blueprint asks for the API scanner host because the scanner must be provisioned as a separate private service; allocate at least 4 GiB RAM and persistent signature storage.
- Complete the EICAR-safe test-file, scanner outage and clean-upload acceptance in an isolated staging environment before enabling customer document uploads. Do not use live malware samples.

## Release decision

RC20 closes the code integration gap for fail-closed antivirus scanning, but the scanner container, signature update path, real S3 integration, Docker/PostgreSQL/Redis/Celery, Vite build, browser tests, backup/restore and deployment gates remain open. FactoryLink 1.0 is not production-ready until these checks have passed in a controlled environment and received customer/security approval.
