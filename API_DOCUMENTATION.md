# API Documentation

Base path: `/api/v1`. All protected routes use `Authorization: Bearer <access_token>`. Interactive OpenAPI documentation is served at `/docs` when the API is running.

## Authentication

Refresh-token rotation assigns a family identifier to each login session. If an already-rotated token is presented again, the API rejects the request and revokes all still-active refresh tokens in that family. Other login sessions for the same account remain independent. The client must sign in again after a replay response.


| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/login` | Validate credentials and issue access + refresh tokens |
| POST | `/auth/refresh` | Rotate refresh token and issue new token pair |
| POST | `/auth/logout` | Revoke the supplied refresh token for the current user |
| GET | `/auth/me` | Current user and organisation context |
| PATCH | `/auth/language` | Set `en` or `ja` preference |

## Organisation and users

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/organizations/register` | Public first-time manufacturer/supplier workspace registration; creates its first user and returns tokens |
| GET | `/organizations/current` | Current organisation profile |
| GET | `/users` | List users in the current organisation (`ORG_ADMIN` or `SUPPLIER_ADMIN`) |
| POST | `/users/invitations` | Create an inactive user and issue a one-time invitation (role validated for organisation type) |

## Operations

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/dashboard` | Tenant-scoped KPI and dashboard records |
| GET / POST | `/suppliers` | Supplier directory and create |
| GET / POST | `/purchase-orders` | List and create purchase orders |
| PATCH | `/purchase-orders/{id}/status` | Supplier confirms then dispatches (`SUBMITTED → CONFIRMED → IN_TRANSIT`); factory can submit/cancel; actual delivery state is set by goods receipt |
| GET | `/inventory/batches` | List lot/batch inventory |
| POST | `/inventory/receipts` | Record a material lot and receipt ledger event; optionally link to `purchase_order_id` to enforce supplier, item, unit and outstanding quantity and update partial/delivered status |
| POST | `/inventory/adjustments` | Apply an authorised, reason-coded stock adjustment without reducing stock below reservations |
| GET / POST | `/production/orders` | List and create production orders |
| PATCH | `/production/orders/{id}/status` | Validate status transition, reserve/consume/release materials |
| PATCH | `/production/orders/{id}/progress` | Update completed/rejected quantities; the web UI exposes this while an order is active or paused |
| GET / POST | `/quality/templates` | List/create tenant-scoped reusable receiving, in-process and final inspection templates |
| GET / POST | `/quality/inspections` | List/record pass/fail inspections; applies optional template criteria and derives FAIL when a criterion fails |
| GET | `/quality/capa` | List corrective/preventive action cases opened by failed inspections |
| PATCH | `/quality/capa/{id}` | Update CAPA owner, due date, evidence and controlled status progression (OPEN → CONTAINED → INVESTIGATING → IMPLEMENTED → VERIFIED → CLOSED) |
| POST | `/quality/batches/{id}/release` | Release a held batch only when the latest linked inspection is PASS and includes documented notes; requires QA/admin role and a release reason |
| GET | `/traceability/{lot_number}` | Forward lot history: supplier/PO, goods receipt, stock ledger, production orders, inspections, CAPA cases and finished serials |
| GET | `/traceability/serials` | List finished-product serials; optional `status` and `limit` filters |
| GET | `/traceability/serials/{serial_number}` | Serial genealogy including production order and source material lots, supplier, PO and inspections |
| PATCH | `/traceability/serials/{serial_number}/shipment` | Record customer and shipment reference for an available serial; source lots on quality hold block shipment and quarantine the serial |
| GET | `/traceability/qr/{kind}/{identifier}.svg` | Generate a tenant-checked QR image for `kind=lot` or `kind=serial`; payload format is `FACTORYLINK:LOT:<id>` or `FACTORYLINK:SERIAL:<id>` |
| GET / POST | `/maintenance/equipment` | Equipment register |
| GET / POST | `/maintenance/tasks` | Maintenance tasks with `PREVENTIVE` or `UNPLANNED` classification |
| PATCH | `/maintenance/tasks/{id}` | Update maintenance state, classification and downtime |
| GET | `/maintenance/analytics` | Preventive/unplanned downtime totals; availability is returned only when planned operating minutes are supplied |
| GET | `/notifications` | List the latest notifications for the current organisation |
| GET | `/notifications/unread-count` | Return the current organisation unread count only |
| PATCH | `/notifications/{id}/read` | Mark one notification read; cross-tenant IDs return 404 |
| PATCH | `/notifications/read-all` | Mark all unread notifications in the current organisation as read |
| GET | `/reports/production.csv` | Export production rows as UTF-8 CSV |
| GET | `/reports/production.xlsx` | Export production rows as XLSX |
| GET | `/reports/inventory.csv` | Export lot-level stock, reservations, availability and JPY valuation as UTF-8 CSV (authenticated manufacturer workspace users; supplier accounts receive HTTP 403) |
| GET | `/reports/inventory.xlsx` | Export lot-level inventory as an Excel workbook |
| GET | `/reports/quality.csv` | Export inspection outcome, sample size, defect rate, linked lot and corrective action as CSV |
| GET | `/reports/quality.xlsx` | Export quality inspection data as an Excel workbook |
| GET / POST | `/documents` | List and upload allowed documents |
| GET | `/documents/{id}/download` | Download a permitted document |
| GET | `/audit` | Recent audit records (ORG_ADMIN) |

## Company onboarding and supplier linking

A manufacturer or supplier can create its own workspace through `POST /api/v1/organizations/register`. The request includes `organization_name`, a unique `organization_code`, `organization_type` (`MANUFACTURER` or `SUPPLIER`), `owner_name`, `email`, `password`, and optional `language`, `postal_code`, and `prefecture`. The first user receives `ORG_ADMIN` for a manufacturer or `SUPPLIER_ADMIN` for a supplier. Public registration is controlled by `ALLOW_PUBLIC_REGISTRATION`; production startup requires it to be disabled. Apply CAPTCHA/rate limiting, verification and an invitation/approval policy before exposing registration publicly.

To link a registered supplier workspace, a factory administrator creates a supplier directory record with `supplier_organization_code` set to the supplier's company code. Purchase orders attached to that directory entry then appear to the linked supplier user(s). Company codes must be shared out-of-band and are not authentication credentials.

Example registration:

```json
{
  "organization_name": "Kyoto Precision Works",
  "organization_code": "KYOTO-PRECISION",
  "organization_type": "MANUFACTURER",
  "owner_name": "Demo Administrator",
  "email": "admin@example.jp",
  "password": "a-unique-password-of-12-chars-or-more",
  "language": "ja",
  "postal_code": "600-8009",
  "prefecture": "京都府"
}
```

## Quality hold and release lifecycle

A quality template stores criteria as structured JSON. Supported criterion kinds are `PASS_FAIL`, `NUMERIC` (optional minimum/maximum bounds) and `TEXT`; required values and unknown keys are validated by the API. A numeric out-of-range result or a `FAIL` criterion makes the inspection fail even if the submitted overall result says `PASS`. A failed inspection with a linked material batch places that batch on `HOLD`, records the failed result and creates a tenant-scoped CAPA case. The CAPA workflow requires containment before investigation, root cause before implementation, both corrective and preventive actions before verification, and verification evidence before closure. A hold is not automatically removed by a later passing inspection. A quality inspector or organisation administrator must call `POST /quality/batches/{id}/release` with the latest passing inspection ID and a release reason. The API verifies that the inspection belongs to the same tenant and batch, is the most recent inspection for that batch, has result `PASS`, and contains documented inspection notes. On success, the batch becomes `AVAILABLE`, an audit record is written, and a `QUALITY_RELEASED` event is added to lot traceability.

## Purchase order and goods receipt lifecycle

A supplier may transition a shared order from `SUBMITTED` to `CONFIRMED`, then from `CONFIRMED` to `IN_TRANSIT`. After a partial factory receipt, the supplier can dispatch the outstanding balance again by transitioning `PARTIALLY_DELIVERED` to `IN_TRANSIT`. A supplier cannot mark an order delivered. A warehouse user records each physical delivery using `POST /inventory/receipts` with the purchase-order ID, lot number, received quantity, item and unit. The API requires `IN_TRANSIT`, checks that the supplier/item/unit match, and prevents cumulative receipts from exceeding the ordered amount. The purchase order becomes `PARTIALLY_DELIVERED` until the cumulative receipt quantity reaches the ordered quantity, at which point it becomes `DELIVERED`. The `received_quantity` total is persisted on the purchase-order row, atomically incremented in the same transaction as each linked receipt, and backfilled from immutable receipt-ledger events during migration `0006`. This allows linked suppliers to see their cumulative and remaining quantities without SELECT access to factory inventory tables. On PostgreSQL, a trigger rejects changes to this total unless the transaction tenant context matches the purchase-order owning factory. `GET /purchase-orders` includes `received_quantity` and `remaining_quantity` from this guarded counter.

Example linked receipt:

```json
{
  "purchase_order_id": 12,
  "material_name": "Steel (S45C)",
  "lot_number": "LOT-2026-001",
  "quantity": 250,
  "unit": "kg",
  "unit_cost": 420,
  "reference": "GR-2026-001"
}
```

A `409` is returned when a receipt would exceed the remaining PO quantity or the PO is not ready to receive. The PO-linked batch retains its purchase-order relationship for traceability.

## Finished-product serial genealogy and QR codes

Production orders have `track_serials` enabled by default. When an order is completed, the backend creates one unique `FP-<order-number>-<sequence>` serial for every accepted completed unit (not rejected quantity), with the consumed source-lot list recorded on each serial. Serialized output must be a whole-number quantity and is capped at 5,000 units per completion; disable serial tracking for bulk-measured output. A serial can be traced back to its production order and source material lots, including supplier, purchase order and quality history. A warehouse/production/admin user records a customer and shipment reference through the shipment endpoint. A serial whose source lot is on quality hold is quarantined and cannot be shipped.

QR downloads return SVG images. The React traceability screen also offers camera scanning on browsers with `BarcodeDetector` support in a secure context; manual search is the fallback.

## Roles in this release

`ORG_ADMIN`, `PRODUCTION_MANAGER`, `WAREHOUSE_MANAGER`, `QUALITY_INSPECTOR`, `MAINTENANCE_MANAGER`, `OPERATOR`, `SUPPLIER_ADMIN`, `SUPPLIER_USER`.

Role checks and tenant-scoped queries are implemented for the main operations. On PostgreSQL, migration `0004_postgresql_tenant_rls` adds defence-in-depth RLS policies to operational tables; migration `0006_supplier_receipt_progress` tightens supplier PO policies to require the supplier record and PO to belong to the same factory. Supplier policies expose only records linked to the supplier workspace. The identity tables (`organizations`, `users`, `refresh_tokens`) remain outside those policies and are accessed through dedicated authentication/registration logic. Factory receipt progress is intentionally exposed through the guarded purchase-order counter, not by granting supplier accounts access to material batches or inventory movements. SQLite tests do not exercise PostgreSQL RLS; validate the included SQL acceptance scripts against a real PostgreSQL instance before production use. This is not a substitute for an independent security review.

## Example: sign in

```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@factorylink.jp","password":"FactoryLink2026!"}'
```

Use the returned `access_token` as a bearer token. Refresh tokens should be stored securely by the client and rotated at `/auth/refresh`. This local sample UI stores tokens in `sessionStorage`; assess your organisation's browser-security policy before production use.

## Authentication and account lifecycle

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| POST | `/api/v1/auth/password-reset/request` | Public, rate-limited | Request a reset link; returns the same generic message for known and unknown email addresses. A development-only action link may be included when explicitly enabled and SMTP is not configured. |
| POST | `/api/v1/auth/password-reset/confirm` | Public, rate-limited | Redeem a 30-minute, single-use password reset token and invalidate all active refresh sessions for that user. |
| POST | `/api/v1/users/invitations` | Organisation administrator | Create an inactive user and send a seven-day invitation link. Role choices are validated against the organisation type. |
| POST | `/api/v1/users/invitations/accept` | Public, rate-limited | Redeem a single-use invitation, set a password, activate the account and establish a session. |

The former `POST /api/v1/users` direct-password assignment endpoint returns HTTP 410. Use invitation creation instead. In production, configure SMTP through environment variables and set `EXPOSE_AUTH_ACTION_LINKS=false`; the API startup guard enforces these requirements and requires an HTTPS `FRONTEND_BASE_URL`.


## Supplier workspace administration

The first account created while registering a `SUPPLIER` organisation has the `SUPPLIER_ADMIN` role. `GET /api/v1/users` and `POST /api/v1/users/invitations` accept either `ORG_ADMIN` in a manufacturer organisation or `SUPPLIER_ADMIN` in a supplier organisation. The invitation role is validated against the organisation type: supplier administrators may invite only `SUPPLIER_USER` colleagues. Both supplier roles remain limited to purchase orders, linked supplier documents and associated supplier notifications.


## RC13 notifications and reporting

The notification centre uses the authenticated organisation as its scope. `GET /notifications/unread-count` returns `{ "unread_count": number }`. `PATCH /notifications/read-all` updates only unread notification rows belonging to the authenticated organisation and returns `{ "updated": number }`. The web UI exposes All, Unread only and Needs attention (WARNING/CRITICAL) filters; filtering is over the latest 50 notification records returned by `GET /notifications`.

Inventory and quality exports are not available to supplier accounts (HTTP 403). Inventory reports include material/lot, on-hand, reserved, available, unit cost and computed stock value in JPY. Quality reports include inspection, product, linked lot, result, defects, sample size, calculated defect rate and corrective action. Exported text is escaped against spreadsheet formula injection; XLSX textual columns are explicitly saved as strings. The APIs scope all rows to the authenticated manufacturer organisation.
