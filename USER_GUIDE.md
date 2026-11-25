# FactoryLink — User Guide

FactoryLink is a local-evaluation manufacturing operations workspace for a fictional Japanese manufacturer and linked suppliers. Use only fictional data while evaluating it.

## 1. Sign in and choose a workspace role

Use the local demo accounts in `README.md`. The navigation and API permissions depend on the authenticated user's organisation membership and role. Supplier accounts are intentionally limited to purchase orders and documents shared with their supplier workspace; they must not access factory inventory, production, quality, traceability, maintenance or internal reports.

## 2. Typical manufacturer workflow

### Procurement and supplier delivery

1. Sign in as the factory administrator or procurement-capable user.
2. Open **Suppliers** and confirm that the supplier workspace is linked using its company code.
3. Open **Purchase Orders** and create a purchase order for the linked supplier.
4. Submit the order so it appears in the supplier portal.
5. Sign in as the supplier user, open **Purchase Orders**, confirm the order and update its delivery status.
6. Sign back in as a warehouse-capable factory user and open **Inventory**.
7. Record a goods receipt against the in-transit purchase order. Use a distinct receipt reference and lot number for each partial delivery.
8. Verify that each receipt creates a material lot and ledger movement. Cumulative received quantity must not exceed the ordered quantity.

### Inventory and production

1. Review available, reserved and on-hand quantities on **Inventory**.
2. Open **Production** and create a production order with the required material quantities.
3. Move the order through the permitted states. Material reservation uses eligible batches and FIFO allocation.
4. Record production progress.
5. Complete the production order. The system consumes reserved materials transactionally and creates one finished-product serial for each accepted unit when serial tracking is enabled. Rejected units are not serialised.
6. A cancelled order releases reservations according to the business rules.

### Quality and corrective action

1. Open **Quality** and review the available inspection templates.
2. Create an inspection for the material lot or finished product batch exposed in the form.
3. Enter the required template criteria and inspection sample/defect data.
4. A failed criterion forces the effective inspection result to FAIL even when a submitted overall result says PASS.
5. A failed lot is placed on quality hold and a CAPA case is opened. The CAPA lifecycle records containment, investigation/root cause, corrective and preventive actions, verification evidence and closure.
6. A held batch cannot be consumed by normal production or shipped. Release is a separate authorised action and requires a later passing inspection plus a documented reason.

### Traceability and shipment

1. Open **Traceability** and search by material lot or finished-product serial.
2. A lot search shows the upstream supplier/purchase order/receipt and downstream production, inspection, CAPA and finished serial relationships that exist for that lot.
3. A serial search shows its production order, source material lots, supplier/purchase order and inspection history.
4. QR codes can be downloaded as SVG. Camera scanning depends on browser `BarcodeDetector` and camera permission; manual identifier entry is the supported fallback.
5. Available finished serials can be assigned to a customer/shipment reference. Serials whose source lots are held are quarantined and cannot be shipped.

### Equipment and maintenance

1. Open **Maintenance** and register equipment.
2. Create preventive maintenance or unplanned repair work records.
3. Complete work with the required downtime information.
4. Review preventive, unplanned and total downtime analytics. Availability is calculated only when planned operating minutes are supplied for the period.

## 3. Dashboard, reports, notifications and audit

- **Dashboard** KPIs are calculated from the authenticated organisation's persisted records.
- **Reports** provide the implemented CSV/XLSX exports. Review date and organisation filters before downloading.
- **Notifications** show relevant in-app operational events and support read/unread handling.
- **Audit logs** record important business actions and are not ordinary editable records.

## 4. Japanese and English

Use the language selector in the application header. English is the default; Japanese labels are maintained in the central translation catalogue. Organisation defaults use `Asia/Tokyo` display timezone and JPY. Database timestamps are stored in UTC. Names, addresses and uploaded data should be UTF-8.

## 5. Safe evaluation practices

- Do not upload real customer, employee, medical, financial or confidential factory records into this local demo.
- Do not use demo accounts or demo secrets in a public deployment.
- Do not treat QR camera scanning as supported in every browser; use manual search if the browser lacks `BarcodeDetector`.
- A failed inspection must not be silently cleared. Follow the documented CAPA and QA release process.
- A rollback cannot universally reverse already completed external operations; inspect the available recovery references and retain backups.
- Do not run `docker compose down -v` unless you intend to delete local data.

This guide describes the implemented local evaluation workflow. Production operation still requires PostgreSQL, storage, ClamAV, backup, security, operational and customer acceptance described in `FINAL_ACCEPTANCE_CHECKLIST.md`.
