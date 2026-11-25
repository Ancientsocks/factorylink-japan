# Inventory invariants

- Tenant ownership is stored on the material batch and every inventory movement.
- A lot number must be unique within its organisation.
- Receipts create a positive movement and a traceability event in the same database transaction as the new batch.
- Reservations consume only free quantity from `AVAILABLE` lots in FIFO receipt order.
- `quantity_reserved` cannot be negative or exceed `quantity_on_hand`.
- Production completion releases the order's reservation and writes a negative consumption movement for each batch allocation.
- Production cancellation releases reservations without reducing on-hand stock.
- Failed quality inspections move a linked batch to `HOLD`, excluding it from new reservations.
- Never update stock directly in an administrative SQL console without recording a compensating movement and audit explanation.
