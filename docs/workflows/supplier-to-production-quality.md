# Supplier-to-production-to-quality workflow

This describes the implemented local core workflow. The API validates transitions, tenant boundaries and inventory invariants; frontend visibility is not the security boundary.

1. A supplier registers a supplier workspace and receives a company code.
2. A factory user registers or signs in, then links the supplier code in the factory supplier directory.
3. A factory administrator or production manager creates a purchase order for that supplier and submits it.
4. The supplier sees only purchase orders linked to its supplier organisation, confirms the order and advances delivery status.
5. A factory warehouse manager records one or more partial/final goods receipts against an eligible in-transit purchase order. Each receipt creates a batch, a positive inventory movement and a traceability event in the same transaction. Over-receipt and unit mismatch are rejected.
6. A quality inspector can run a reusable receiving, in-process or final inspection template. Required fields and numeric tolerances are validated server-side. A failed criterion determines an effective `FAIL` result even if a submitted overall result says `PASS`.
7. A failed inspection places its linked batch on `HOLD` and opens one CAPA case. CAPA transitions are evidence-gated: `OPEN → CONTAINED → INVESTIGATING → IMPLEMENTED → VERIFIED → CLOSED`.
8. A held batch is unavailable for normal production reservation/consumption and cannot be used to ship finished serials. Release is an explicit authorised action requiring the latest inspection to pass and a documented release reason.
9. A production manager creates a production order and moves it to `READY`. The API reserves eligible stock FIFO in a transaction. Operators record progress; completion consumes reserved material and records negative stock movements and traceability events. Cancellation releases active reservations.
10. Serial-tracked production creates one unique finished-product serial per accepted completed unit. Each serial links to its production order and source material lots; rejected units are not serialised.
11. A factory user can search a material lot forward into production orders, inspections, CAPA and finished serials, or search a finished serial backward into its source material lots and supplier/PO/receipt history. SVG QR codes are downloadable; browser camera scanning is available where `BarcodeDetector` and camera permission are supported, with manual search as fallback.
12. Available finished serials can be assigned a customer and shipment reference. A serial linked to a held source lot is quarantined and cannot be shipped.

## Important state and integrity rules

- Purchase order: `DRAFT → SUBMITTED → CONFIRMED → PARTIALLY_DELIVERED → DELIVERED`; only supported states can be cancelled.
- Production: `DRAFT → PLANNED → READY → IN_PROGRESS → PAUSED → IN_PROGRESS → COMPLETED`; cancellation releases active reservations.
- Quality: `PASS`/`FAIL` is derived from required inspection criteria and recorded sample results. Failed results open CAPA and hold the material lot. A later passing inspection alone does not clear the hold.
- Available quantity is on-hand minus reserved quantity. Negative stock and over-reservation are prevented by constraints and transactional logic.
- Every stock movement, material receipt, production consumption, quality event, CAPA transition, serial creation/shipment and relevant administrative operation is recorded for audit/traceability.
- Supplier company codes are linking identifiers, not authentication credentials. Share them out-of-band.

The sample companies, users, product names and transaction records are fictional.
