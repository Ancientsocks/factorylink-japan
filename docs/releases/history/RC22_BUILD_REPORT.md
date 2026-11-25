# FactoryLink RC22 Build Report — core manufacturing workflow completion

**Release:** `1.0.0-rc.22`  
**Date:** 2026-11-03  
**Status:** Local core-complete candidate for user-run acceptance. Not production-certified or approved for live factory data.

## Scope delivered

RC22 closes the previously identified core workflow gaps from the FactoryLink master prompt without changing the product direction.

- **Quality templates:** tenant-scoped reusable inspection templates with `PASS_FAIL`, `NUMERIC` (optional min/max) and `TEXT` criteria. Required and unknown fields are validated; numeric out-of-range or failed criteria force the effective inspection result to `FAIL`, even if the submitted overall result says `PASS`.
- **CAPA:** each failed inspection opens one tenant-scoped corrective/preventive-action case. The case has a controlled, evidence-gated lifecycle: `OPEN → CONTAINED → INVESTIGATING → IMPLEMENTED → VERIFIED → CLOSED`. It records containment, root cause, corrective and preventive actions, verification, owner, due date, audit events and lot-trace events.
- **Quality holds:** a failed inspection places its linked batch on hold. A later passing inspection does not silently release it; explicit release requires the latest passing inspection and a documented release reason.
- **Finished-product serialisation:** production orders support serial tracking (enabled by default). Completion generates one unique serial for each accepted completed unit and links the serial to the material lots reserved/consumed for that order. Rejected units are not serialised. Bulk-measured production can disable serial tracking.
- **Traceability:** lot trace results now include supplier, purchase order, receipt/stock events, downstream production orders, inspections, CAPA and finished serials. Serial lookup returns its production order, source material lots, supplier/PO and inspection history.
- **QR and shipment:** the API generates downloadable SVG QR codes for material lots and finished serials. The browser UI uses `BarcodeDetector` camera scanning where supported and provides manual search as a fallback. Available serials can be shipped to a named customer with a shipment reference; a serial linked to a held source lot is quarantined and cannot ship.
- **Maintenance:** maintenance work is classified as `PREVENTIVE` or `UNPLANNED`. Tenant-scoped analytics report preventive, unplanned and total downtime; availability is calculated only when the caller supplies planned operating minutes for the reporting period.
- **UI and documentation:** Quality, Traceability and Maintenance workspaces are connected to the new APIs. Japanese/English status labels were added. API and database documentation, README, project status, changelog and this report were updated.

## Verification performed

The following backend regression groups were executed successfully during RC22 work:

| Test group | Result |
|---|---:|
| `tests/test_api.py` | 71 passed (executed in smaller batches) |
| `tests/test_release_integrity.py tests/test_admin_bootstrap.py tests/test_render_deploy.py` | 40 passed |
| `tests/test_mailer.py tests/test_malware_scanner.py tests/test_object_storage.py` | 19 passed |
| **Total backend regression tests** | **130 passed** |

Additional checks:

- Targeted RC22 workflow regression tests: **3 passed** (template-derived failure and CAPA lifecycle; serial generation, genealogy, QR and shipment; maintenance downtime classification/analytics).
- Fresh SQLite Alembic migration through `0007_quality_capa_serial_traceability` completed successfully.
- Repeatable local demo seed completed successfully and created the quality template and demo CAPA case.
- `python -m compileall -q app migrations tests` passed.
- TypeScript `transpileModule` syntax check on `frontend/src/App.tsx` and `frontend/src/i18n.ts`: **0 syntax diagnostics**. This is a syntax/transpilation check, not a dependency-backed typecheck or Vite production build.
- The release-integrity checks verify frontend API paths against the FastAPI route table.

## Not executed in this build environment

These checks require local tools, services, external credentials or a real browser and must not be interpreted as passed:

- Docker Compose image build/start and full local stack runtime.
- Dependency-backed Vite production build, TypeScript typecheck with installed packages, and Playwright browser journeys. `npm install --no-audit --no-fund` timed out in this environment; no successful `npm run build` is claimed.
- Real PostgreSQL 17 RLS/ACL/trigger/concurrency acceptance; SQLite migration success does not prove PostgreSQL policy or grant behaviour.
- Real Redis/Celery worker and scheduler runtime.
- Real ClamAV 1.5 signature warm-up, EICAR rejection and clean-file upload; scanner protocol tests use a fake daemon.
- Real S3/IAM integration, backup/restore drill, k6 load run, independent security review, staging deployment or customer acceptance.

Docker, PostgreSQL and Redis executables/services were unavailable in the build environment. The user should run the packaged application locally with Docker Desktop and verify the real browser workflow before considering it accepted for their machine.

## Local run

Windows PowerShell (from the extracted project root):

```powershell
.\scripts\start.ps1
```

macOS/Linux:

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

Open `http://localhost:8080`. The first run requires internet access to download container images and install/build frontend dependencies. The ClamAV signature database needs additional memory; allocate approximately 4 GiB or more to Docker Desktop as described in the deployment guide. The local demo accounts and password are listed in `README.md`.

## Release decision

RC22 implements the identified core functionality gaps in the original FactoryLink local product scope and is packaged for the user's local run and defect feedback. It is **not certified, production-approved or proven against real factory infrastructure**. Use fictional demo data only until the Docker/browser/PostgreSQL/Redis/ClamAV checks and the customer's own security, operational, Japanese-language and business-process acceptance have been completed.
