"""Smoke-test a live FactoryLink API connected as the restricted PostgreSQL role."""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json

BASE_URL = os.getenv("FACTORYLINK_BASE_URL", "http://127.0.0.1:8000")


def request(path: str, *, method: str = "GET", payload: dict | None = None, token: str | None = None):
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
            return response.status, json.loads(data) if "json" in content_type and data else data
    except HTTPError as exc:
        data = exc.read()
        try:
            parsed = json.loads(data) if data else None
        except json.JSONDecodeError:
            parsed = data.decode(errors="replace")
        return exc.code, parsed


def login(email: str) -> dict:
    status, data = request("/api/v1/auth/login", method="POST", payload={"email": email, "password": "FactoryLink2026!"})
    assert status == 200, f"Login failed for {email}: HTTP {status} {data}"
    assert data.get("access_token") and data.get("refresh_token"), f"Token response incomplete for {email}"
    return data


def main() -> None:
    for _ in range(40):
        try:
            status, body = request("/health")
            if status == 200:
                break
        except (URLError, TimeoutError):
            time.sleep(1)
    else:
        raise SystemExit("FactoryLink API did not become healthy")

    factory = login("admin@factorylink.jp")
    supplier = login("supplier@osaka-parts.jp")
    warehouse = login("warehouse@factorylink.jp")
    quality = login("quality@factorylink.jp")
    production = login("production@factorylink.jp")
    other_factory = login("admin@tokyo-industrial.jp")

    status, dashboard = request("/api/v1/dashboard", token=factory["access_token"])
    assert status == 200 and dashboard.get("kpis", {}).get("production_orders", 0) >= 1, f"Factory dashboard failed: {status} {dashboard}"

    status, batches = request("/api/v1/inventory/batches", token=factory["access_token"])
    assert status == 200 and len(batches) >= 1, f"Factory inventory read failed: {status} {batches}"

    status, orders = request("/api/v1/purchase-orders", token=supplier["access_token"])
    assert status == 200 and len(orders) >= 1, f"Supplier linked purchase orders failed: {status} {orders}"
    steel_order = next((row for row in orders if row.get("po_number") == "PO-2026-001"), None)
    resin_order = next((row for row in orders if row.get("po_number") == "PO-2026-002"), None)
    assert steel_order and steel_order.get("received_quantity") == 3200 and steel_order.get("remaining_quantity") == 800, f"Supplier steel receipt progress is incorrect: {steel_order}"
    assert resin_order and resin_order.get("received_quantity") == 1500 and resin_order.get("remaining_quantity") == 500, f"Supplier resin receipt progress is incorrect: {resin_order}"

    status, denied = request("/api/v1/inventory/batches", token=supplier["access_token"])
    assert status == 403, f"Supplier unexpectedly accessed factory inventory: {status} {denied}"

    # Exercise the PostgreSQL-only receipt counter update and trigger using the
    # restricted runtime DB role: create → submit → supplier confirm/dispatch
    # → warehouse receipt → supplier reads the progress without ledger access.
    status, suppliers = request("/api/v1/suppliers", token=factory["access_token"])
    assert status == 200 and suppliers, f"Factory supplier directory failed: {status} {suppliers}"
    supplier_me_status, supplier_me = request("/api/v1/auth/me", token=supplier["access_token"])
    assert supplier_me_status == 200, f"Supplier identity lookup failed: {supplier_me_status} {supplier_me}"
    linked_supplier = next((row for row in suppliers if row.get("supplier_organization_id") == supplier_me.get("organization_id")), None)
    assert linked_supplier, f"No supplier link found for demo supplier organisation {supplier_me.get('organization_id')}"

    suffix = str(time.time_ns())
    po_number = f"PG-ACCEPT-{suffix[-12:]}"
    lot_number = f"PG-LOT-{suffix[-12:]}"
    reference = f"PG-REF-{suffix[-12:]}"
    status, created_po = request("/api/v1/purchase-orders", method="POST", payload={
        "supplier_id": linked_supplier["id"], "po_number": po_number,
        "item_name": "PostgreSQL Acceptance Part", "quantity": 5,
        "unit": "pcs", "unit_price": 1.0,
    }, token=factory["access_token"])
    assert status == 201, f"Runtime factory PO creation failed: {status} {created_po}"
    po_id = created_po["id"]

    status, submitted = request(f"/api/v1/purchase-orders/{po_id}/status", method="PATCH", payload={"status": "SUBMITTED"}, token=factory["access_token"])
    assert status == 200, f"Factory PO submission failed: {status} {submitted}"
    status, confirmed = request(f"/api/v1/purchase-orders/{po_id}/status", method="PATCH", payload={"status": "CONFIRMED"}, token=supplier["access_token"])
    assert status == 200, f"Supplier PO confirmation failed: {status} {confirmed}"
    status, dispatched = request(f"/api/v1/purchase-orders/{po_id}/status", method="PATCH", payload={"status": "IN_TRANSIT"}, token=supplier["access_token"])
    assert status == 200, f"Supplier PO dispatch failed: {status} {dispatched}"

    status, receipt = request("/api/v1/inventory/receipts", method="POST", payload={
        "purchase_order_id": po_id, "material_name": "PostgreSQL Acceptance Part",
        "lot_number": lot_number, "quantity": 2, "unit": "pcs",
        "unit_cost": 1.0, "reference": reference,
    }, token=factory["access_token"])
    assert status == 201, f"Runtime factory goods receipt failed: {status} {receipt}"

    status, latest_orders = request("/api/v1/purchase-orders", token=supplier["access_token"])
    assert status == 200, f"Supplier could not refresh PO receipt progress: {status} {latest_orders}"
    accepted_po = next((row for row in latest_orders if row.get("po_number") == po_number), None)
    assert accepted_po and accepted_po.get("received_quantity") == 2 and accepted_po.get("remaining_quantity") == 3, f"Supplier-visible PostgreSQL receipt total is incorrect: {accepted_po}"
    assert accepted_po.get("status") == "PARTIALLY_DELIVERED", f"Partial receipt status was not committed: {accepted_po}"

    # Exercise the complete tenant workflow through the restricted PostgreSQL
    # runtime role. Every name is unique so prior acceptance runs remain intact.
    flow_suffix = str(time.time_ns())[-12:]
    flow_po_number = f"PG-FLOW-{flow_suffix}"
    flow_lot_number = f"PG-FLOW-LOT-{flow_suffix}"
    flow_reference = f"PG-FLOW-GR-{flow_suffix}"
    flow_item = f"PG Workflow Component {flow_suffix}"
    flow_order_number = f"PG-MO-{flow_suffix}"

    status, supplier_rows = request("/api/v1/suppliers", token=factory["access_token"])
    assert status == 200 and supplier_rows, f"Factory supplier lookup failed: {status} {supplier_rows}"
    linked_flow_supplier = next(
        (row for row in supplier_rows if row.get("supplier_organization_id") == supplier_me.get("organization_id")),
        None,
    )
    assert linked_flow_supplier, f"Supplier link disappeared for organisation {supplier_me.get('organization_id')}"

    status, flow_po = request("/api/v1/purchase-orders", method="POST", payload={
        "supplier_id": linked_flow_supplier["id"], "po_number": flow_po_number,
        "item_name": flow_item, "quantity": 5, "unit": "pcs", "unit_price": 250,
    }, token=factory["access_token"])
    assert status == 201, f"PostgreSQL workflow PO creation failed: {status} {flow_po}"
    flow_po_id = flow_po["id"]

    status, invalid_po_transition = request(
        f"/api/v1/purchase-orders/{flow_po_id}/status", method="PATCH",
        payload={"status": "CONFIRMED"}, token=factory["access_token"],
    )
    assert status == 409, f"Draft PO accepted an invalid state transition: {status} {invalid_po_transition}"
    status, cross_org_po_update = request(
        f"/api/v1/purchase-orders/{flow_po_id}/status", method="PATCH",
        payload={"status": "CANCELLED"}, token=other_factory["access_token"],
    )
    assert status == 404, f"Another organisation discovered or changed this PO: {status} {cross_org_po_update}"
    status, supplier_inventory = request("/api/v1/inventory/batches", token=supplier["access_token"])
    assert status == 403, f"Supplier accessed the factory inventory: {status} {supplier_inventory}"

    status, submitted = request(
        f"/api/v1/purchase-orders/{flow_po_id}/status", method="PATCH",
        payload={"status": "SUBMITTED"}, token=factory["access_token"],
    )
    assert status == 200, f"Factory PO submission failed: {status} {submitted}"
    status, confirmed = request(
        f"/api/v1/purchase-orders/{flow_po_id}/status", method="PATCH",
        payload={"status": "CONFIRMED"}, token=supplier["access_token"],
    )
    assert status == 200, f"Supplier PO confirmation failed: {status} {confirmed}"

    status, pre_dispatch_receipt = request("/api/v1/inventory/receipts", method="POST", payload={
        "purchase_order_id": flow_po_id, "material_name": flow_item,
        "lot_number": flow_lot_number, "quantity": 3, "unit": "pcs",
        "unit_cost": 250, "reference": flow_reference,
    }, token=warehouse["access_token"])
    assert status == 409, f"Factory received a PO before supplier dispatch: {status} {pre_dispatch_receipt}"
    status, dispatched = request(
        f"/api/v1/purchase-orders/{flow_po_id}/status", method="PATCH",
        payload={"status": "IN_TRANSIT"}, token=supplier["access_token"],
    )
    assert status == 200, f"Supplier PO dispatch failed: {status} {dispatched}"

    status, flow_receipt = request("/api/v1/inventory/receipts", method="POST", payload={
        "purchase_order_id": flow_po_id, "material_name": flow_item,
        "lot_number": flow_lot_number, "quantity": 3, "unit": "pcs",
        "unit_cost": 250, "reference": flow_reference,
    }, token=warehouse["access_token"])
    assert status == 201, f"PostgreSQL linked goods receipt failed: {status} {flow_receipt}"
    flow_batch_id = flow_receipt["id"]

    status, duplicate_receipt = request("/api/v1/inventory/receipts", method="POST", payload={
        "purchase_order_id": flow_po_id, "material_name": flow_item,
        "lot_number": flow_lot_number, "quantity": 1, "unit": "pcs",
        "unit_cost": 250, "reference": f"{flow_reference}-DUP",
    }, token=warehouse["access_token"])
    assert status == 409, f"Duplicate lot receipt was accepted: {status} {duplicate_receipt}"
    status, excessive_receipt = request("/api/v1/inventory/receipts", method="POST", payload={
        "purchase_order_id": flow_po_id, "material_name": flow_item,
        "lot_number": f"{flow_lot_number}-EXTRA", "quantity": 3, "unit": "pcs",
        "unit_cost": 250, "reference": f"{flow_reference}-EXTRA",
    }, token=warehouse["access_token"])
    assert status == 409, f"Receipt exceeding the PO balance was accepted: {status} {excessive_receipt}"

    status, inventory = request("/api/v1/inventory/batches", token=factory["access_token"])
    flow_batch = next((row for row in inventory if row.get("id") == flow_batch_id), None) if status == 200 else None
    assert flow_batch and flow_batch["quantity_on_hand"] == 3 and flow_batch["status"] == "AVAILABLE", (
        f"Received lot was not persisted correctly: HTTP {status} {flow_batch}"
    )
    def adjust_concurrently(delta: int, suffix: str):
        return request(
            "/api/v1/inventory/adjustments",
            method="POST",
            payload={
                "batch_id": flow_batch_id,
                "quantity_delta": delta,
                "reference": f"{flow_reference}-CONCURRENT-{suffix}",
                "reason": "PostgreSQL concurrent inventory acceptance",
            },
            token=warehouse["access_token"],
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        increase = pool.submit(adjust_concurrently, 1, "IN")
        decrease = pool.submit(adjust_concurrently, -1, "OUT")
        scan = pool.submit(
            request,
            "/api/v1/inventory/reconciliations",
            method="POST",
            token=warehouse["access_token"],
        )
        increase_result = increase.result()
        decrease_result = decrease.result()
        scan_result = scan.result()
    assert increase_result[0] == 201, f"Concurrent stock increase failed: {increase_result}"
    assert decrease_result[0] == 201, f"Concurrent stock decrease failed: {decrease_result}"
    assert scan_result[0] == 201, f"Concurrent reconciliation scan failed: {scan_result}"
    assert not any(
        row.get("batch_id") == flow_batch_id
        for row in scan_result[1].get("discrepancies", [])
    ), f"Concurrent stock operations left a false reconciliation variance: {scan_result[1]}"
    status, inventory_after_concurrency = request("/api/v1/inventory/batches", token=factory["access_token"])
    concurrent_batch = next(
        (row for row in inventory_after_concurrency if row.get("id") == flow_batch_id),
        None,
    ) if status == 200 else None
    assert concurrent_batch and concurrent_batch["quantity_on_hand"] == 3, (
        f"Concurrent stock updates lost or duplicated a quantity: HTTP {status} {concurrent_batch}"
    )

    status, supplier_order_list = request("/api/v1/purchase-orders", token=supplier["access_token"])
    supplier_flow_po = next(
        (row for row in supplier_order_list if row.get("id") == flow_po_id), None,
    ) if status == 200 else None
    assert supplier_flow_po and supplier_flow_po.get("received_quantity") == 3 and supplier_flow_po.get("remaining_quantity") == 2, (
        f"Supplier receipt progress did not reflect the committed goods receipt: HTTP {status} {supplier_flow_po}"
    )

    status, foreign_po_receipt = request("/api/v1/inventory/receipts", method="POST", payload={
        "purchase_order_id": flow_po_id, "material_name": flow_item,
        "lot_number": f"{flow_lot_number}-FOREIGN", "quantity": 1, "unit": "pcs",
        "unit_cost": 250, "reference": f"{flow_reference}-FOREIGN",
    }, token=other_factory["access_token"])
    assert status == 404, f"Other factory received against a foreign PO: {status} {foreign_po_receipt}"

    status, receiving_inspection = request("/api/v1/quality/inspections", method="POST", payload={
        "inspection_number": f"PG-QI-RCV-{flow_suffix}", "product_name": flow_item,
        "batch_id": flow_batch_id, "result": "PASS", "defect_count": 0, "sample_size": 3,
        "notes": "Receiving inspection passed; dimensional and surface checks recorded.",
    }, token=quality["access_token"])
    assert status == 201 and receiving_inspection.get("result") == "PASS", (
        f"Receiving quality approval failed: {status} {receiving_inspection}"
    )

    status, short_order = request("/api/v1/production/orders", method="POST", payload={
        "order_number": f"{flow_order_number}-SHORT", "product_name": "PG Finished Part",
        "quantity": 2, "material_name": flow_item, "material_required": 4,
        "track_serials": True,
    }, token=production["access_token"])
    assert status == 201, f"Insufficient-stock test order creation failed: {status} {short_order}"
    status, insufficient_reservation = request(
        f"/api/v1/production/orders/{short_order['id']}/status", method="PATCH",
        payload={"status": "READY"}, token=production["access_token"],
    )
    assert status == 409, f"Production reserved more stock than was received: {status} {insufficient_reservation}"
    status, invalid_production_transition = request(
        f"/api/v1/production/orders/{short_order['id']}/status", method="PATCH",
        payload={"status": "IN_PROGRESS"}, token=production["access_token"],
    )
    assert status == 409, f"Planned production order skipped READY: {status} {invalid_production_transition}"

    status, flow_order = request("/api/v1/production/orders", method="POST", payload={
        "order_number": flow_order_number, "product_name": "PG Finished Part",
        "quantity": 2, "material_name": flow_item, "material_required": 2,
        "track_serials": True,
    }, token=production["access_token"])
    assert status == 201, f"Production order creation failed: {status} {flow_order}"
    status, ready_order = request(
        f"/api/v1/production/orders/{flow_order['id']}/status", method="PATCH",
        payload={"status": "READY"}, token=production["access_token"],
    )
    assert status == 200, f"Production material reservation failed: {status} {ready_order}"
    status, in_progress_order = request(
        f"/api/v1/production/orders/{flow_order['id']}/status", method="PATCH",
        payload={"status": "IN_PROGRESS"}, token=production["access_token"],
    )
    assert status == 200, f"Production start failed: {status} {in_progress_order}"
    status, progress = request(
        f"/api/v1/production/orders/{flow_order['id']}/progress", method="PATCH",
        payload={"completed_quantity": 2, "rejected_quantity": 0}, token=production["access_token"],
    )
    assert status == 200, f"Production progress update failed: {status} {progress}"
    status, completed_order = request(
        f"/api/v1/production/orders/{flow_order['id']}/status", method="PATCH",
        payload={"status": "COMPLETED"}, token=production["access_token"],
    )
    assert status == 200, f"Production completion/consumption failed: {status} {completed_order}"

    status, inventory_after_consumption = request("/api/v1/inventory/batches", token=factory["access_token"])
    consumed_batch = next(
        (row for row in inventory_after_consumption if row.get("id") == flow_batch_id),
        None,
    ) if status == 200 else None
    assert consumed_batch and consumed_batch["quantity_on_hand"] == 1 and consumed_batch["quantity_reserved"] == 0, (
        f"Production consumption/reservation release was incorrect: HTTP {status} {consumed_batch}"
    )
    status, serial_rows = request("/api/v1/traceability/serials", token=factory["access_token"])
    flow_serials = [row for row in serial_rows if row.get("production_order_id") == flow_order["id"]] if status == 200 else []
    assert status == 200 and len(flow_serials) == 2, f"Finished-product serial generation failed: {status} {flow_serials}"
    shipped_serial, held_serial = flow_serials

    status, finished_batches = request("/api/v1/quality/finished-batches", token=factory["access_token"])
    finished_batch = next(
        (row for row in finished_batches if row.get("production_order_id") == flow_order["id"]),
        None,
    ) if status == 200 else None
    assert finished_batch, f"Production completion did not create a finished-product batch: HTTP {status} {finished_batches}"
    status, failed_finished_inspection = request("/api/v1/quality/inspections", method="POST", payload={
        "inspection_number": f"PG-QI-FP-FAIL-{flow_suffix}",
        "product_name": "PG Finished Part",
        "finished_product_serial_id": shipped_serial["id"],
        "result": "FAIL", "defect_count": 1, "sample_size": 1,
        "corrective_action": "Quarantine the finished output and investigate the final inspection defect.",
    }, token=quality["access_token"])
    assert status == 201 and failed_finished_inspection.get("result") == "FAIL", (
        f"Finished-product serial inspection failed: {status} {failed_finished_inspection}"
    )
    assert failed_finished_inspection.get("finished_product_batch_id") == finished_batch["id"]
    assert failed_finished_inspection.get("finished_product_serial_id") == shipped_serial["id"]
    assert failed_finished_inspection.get("capa", {}).get("finished_product_batch_id") == finished_batch["id"]
    status, held_finished_batches = request("/api/v1/quality/finished-batches", token=factory["access_token"])
    held_finished_batch = next(
        (row for row in held_finished_batches if row.get("id") == finished_batch["id"]),
        None,
    ) if status == 200 else None
    assert held_finished_batch and held_finished_batch["status"] == "HOLD", (
        f"Failed finished-product inspection did not hold its batch: HTTP {status} {held_finished_batch}"
    )
    status, quarantined_serials = request("/api/v1/traceability/serials", token=factory["access_token"])
    quarantined_flow_serials = [
        row for row in quarantined_serials if row.get("production_order_id") == flow_order["id"]
    ] if status == 200 else []
    assert len(quarantined_flow_serials) == 2 and all(
        row["status"] == "QUARANTINED" for row in quarantined_flow_serials
    ), f"Finished-product batch failure did not quarantine all available serials: {status} {quarantined_flow_serials}"
    status, invalid_finished_release = request(
        f"/api/v1/quality/finished-batches/{finished_batch['id']}/release",
        method="POST",
        payload={"inspection_id": failed_finished_inspection["id"], "reason": "Attempt to release failed finished product"},
        token=quality["access_token"],
    )
    assert status == 409, f"Failed finished-product inspection was released: {status} {invalid_finished_release}"
    capa_id = failed_finished_inspection["capa"]["id"]
    status, invalid_capa_transition = request(
        f"/api/v1/quality/capa/{capa_id}", method="PATCH",
        payload={"status": "CLOSED"}, token=quality["access_token"],
    )
    assert status == 409, f"Finished-product CAPA skipped required corrective-action stages: {status} {invalid_capa_transition}"

    status, failed_source_inspection = request("/api/v1/quality/inspections", method="POST", payload={
        "inspection_number": f"PG-QI-SOURCE-HOLD-{flow_suffix}",
        "product_name": flow_item, "batch_id": flow_batch_id,
        "result": "FAIL", "defect_count": 1, "sample_size": 2,
        "corrective_action": "Contain the source material and investigate the nonconformance.",
    }, token=quality["access_token"])
    assert status == 201 and failed_source_inspection.get("result") == "FAIL", (
        f"Source-material hold setup failed: {status} {failed_source_inspection}"
    )

    status, passing_finished_inspection = request("/api/v1/quality/inspections", method="POST", payload={
        "inspection_number": f"PG-QI-FP-PASS-{flow_suffix}",
        "product_name": "PG Finished Part",
        "finished_product_batch_id": finished_batch["id"],
        "finished_product_serial_id": shipped_serial["id"],
        "result": "PASS", "defect_count": 0, "sample_size": 1,
        "notes": "Corrective action verified; the finished-product reinspection passed all release checks.",
    }, token=quality["access_token"])
    assert status == 201 and passing_finished_inspection.get("result") == "PASS", (
        f"Finished-product reinspection failed: {status} {passing_finished_inspection}"
    )
    status, blocked_finished_release = request(
        f"/api/v1/quality/finished-batches/{finished_batch['id']}/release",
        method="POST",
        payload={
            "inspection_id": passing_finished_inspection["id"],
            "reason": "A held source material lot must block release.",
        },
        token=quality["access_token"],
    )
    assert status == 409, f"Finished-product release bypassed a held source material lot: {status} {blocked_finished_release}"
    status, quarantined_during_source_hold = request("/api/v1/traceability/serials", token=factory["access_token"])
    held_flow_serials = [
        row for row in quarantined_during_source_hold if row.get("production_order_id") == flow_order["id"]
    ] if status == 200 else []
    assert len(held_flow_serials) == 2 and all(
        row["status"] == "QUARANTINED" for row in held_flow_serials
    ), f"Source hold was bypassed and serial quarantine cleared: {status} {held_flow_serials}"

    status, passing_source_inspection = request("/api/v1/quality/inspections", method="POST", payload={
        "inspection_number": f"PG-QI-SOURCE-PASS-{flow_suffix}",
        "product_name": flow_item, "batch_id": flow_batch_id,
        "result": "PASS", "defect_count": 0, "sample_size": 2,
        "notes": "Source material reinspection passed and containment was verified.",
    }, token=quality["access_token"])
    assert status == 201 and passing_source_inspection.get("result") == "PASS", (
        f"Source-material reinspection failed: {status} {passing_source_inspection}"
    )
    status, released_source_batch = request(
        f"/api/v1/quality/batches/{flow_batch_id}/release",
        method="POST",
        payload={
            "inspection_id": passing_source_inspection["id"],
            "reason": "Release the source material after its passing reinspection.",
        },
        token=quality["access_token"],
    )
    assert status == 200 and released_source_batch.get("status") == "AVAILABLE", (
        f"Controlled source-material release failed: {status} {released_source_batch}"
    )

    status, released_finished_batch = request(
        f"/api/v1/quality/finished-batches/{finished_batch['id']}/release",
        method="POST",
        payload={
            "inspection_id": passing_finished_inspection["id"],
            "reason": "Reinspection passed after corrective action verification.",
        },
        token=quality["access_token"],
    )
    assert status == 200 and released_finished_batch.get("status") == "AVAILABLE", (
        f"Controlled finished-product release failed: {status} {released_finished_batch}"
    )
    status, released_serials = request("/api/v1/traceability/serials", token=factory["access_token"])
    released_flow_serials = [
        row for row in released_serials if row.get("production_order_id") == flow_order["id"]
    ] if status == 200 else []
    assert len(released_flow_serials) == 2 and all(
        row["status"] == "AVAILABLE" for row in released_flow_serials
    ), f"Finished-product batch release did not restore quarantined serials: {status} {released_flow_serials}"
    status, finished_serial_genealogy = request(
        f"/api/v1/traceability/serials/{shipped_serial['serial_number']}",
        token=factory["access_token"],
    )
    finished_history = finished_serial_genealogy.get("finished_product_inspections", []) if status == 200 else []
    assert status == 200 and {row.get("inspection_number") for row in finished_history} == {
        failed_finished_inspection["inspection_number"],
        passing_finished_inspection["inspection_number"],
    }, f"Backward trace omitted finished-product inspection history: {status} {finished_serial_genealogy}"
    assert any(
        row.get("case_number") == failed_finished_inspection["capa"]["case_number"]
        for row in finished_serial_genealogy.get("finished_product_corrective_actions", [])
    ), f"Backward trace omitted the finished-product CAPA: {finished_serial_genealogy}"
    status, other_batches = request("/api/v1/quality/finished-batches", token=other_factory["access_token"])
    assert status == 200 and all(row.get("id") != finished_batch["id"] for row in other_batches), (
        f"Finished-product batch crossed organisation boundary: {status} {other_batches}"
    )
    status, foreign_finished_inspection = request("/api/v1/quality/inspections", method="POST", payload={
        "inspection_number": f"PG-QI-FP-XORG-{flow_suffix}",
        "product_name": "PG Finished Part", "finished_product_batch_id": finished_batch["id"],
        "result": "PASS", "defect_count": 0, "sample_size": 1,
        "notes": "Must not create a cross-organisation inspection.",
    }, token=other_factory["access_token"])
    assert status == 404, f"Cross-organisation finished-product inspection was accepted: {status} {foreign_finished_inspection}"

    status, final_inspection = request("/api/v1/quality/inspections", method="POST", payload={
        "inspection_number": f"PG-QI-FINAL-{flow_suffix}", "product_name": "PG Finished Part",
        "batch_id": flow_batch_id, "result": "PASS", "defect_count": 0, "sample_size": 2,
        "notes": "Finished-product inspection passed; all serial labels and dimensions verified.",
    }, token=quality["access_token"])
    assert status == 201 and final_inspection.get("result") == "PASS", (
        f"Finished-product quality inspection failed: {status} {final_inspection}"
    )
    status, shipment = request(
        f"/api/v1/traceability/serials/{shipped_serial['serial_number']}/shipment",
        method="PATCH",
        payload={"customer_name": "PostgreSQL Acceptance Customer", "shipment_reference": f"PG-SHIP-{flow_suffix}"},
        token=warehouse["access_token"],
    )
    assert status == 200 and shipment.get("status") == "SHIPPED", f"Finished serial shipment failed: {status} {shipment}"

    status, failed_inspection = request("/api/v1/quality/inspections", method="POST", payload={
        "inspection_number": f"PG-QI-HOLD-{flow_suffix}", "product_name": flow_item,
        "batch_id": flow_batch_id, "result": "FAIL", "defect_count": 1, "sample_size": 3,
        "corrective_action": "Contain the remaining material and investigate the nonconformance.",
    }, token=quality["access_token"])
    assert status == 201 and failed_inspection.get("result") == "FAIL", (
        f"Quality failure/hold test failed: {status} {failed_inspection}"
    )
    status, hold_inventory = request("/api/v1/inventory/batches", token=factory["access_token"])
    held_batch = next((row for row in hold_inventory if row.get("id") == flow_batch_id), None) if status == 200 else None
    assert held_batch and held_batch["status"] == "HOLD", f"Failed QA did not place the batch on hold: HTTP {status} {held_batch}"
    status, held_serial_shipment = request(
        f"/api/v1/traceability/serials/{held_serial['serial_number']}/shipment",
        method="PATCH",
        payload={"customer_name": "PostgreSQL Acceptance Customer", "shipment_reference": f"PG-SHIP-HOLD-{flow_suffix}"},
        token=warehouse["access_token"],
    )
    assert status == 409, f"A serial sourced from a held lot was shipped: {status} {held_serial_shipment}"
    status, held_serial_trace = request(
        f"/api/v1/traceability/serials/{held_serial['serial_number']}", token=factory["access_token"],
    )
    assert status == 200 and held_serial_trace["serial"]["status"] == "QUARANTINED", (
        f"Held source serial was not quarantined: {status} {held_serial_trace}"
    )
    status, held_production_order = request("/api/v1/production/orders", method="POST", payload={
        "order_number": f"{flow_order_number}-HELD", "product_name": "PG Held Part",
        "quantity": 1, "material_name": flow_item, "material_required": 1,
        "track_serials": True,
    }, token=production["access_token"])
    assert status == 201, f"Hold verification order creation failed: {status} {held_production_order}"
    status, held_reservation = request(
        f"/api/v1/production/orders/{held_production_order['id']}/status", method="PATCH",
        payload={"status": "READY"}, token=production["access_token"],
    )
    assert status == 409, f"Production reserved material from a quality-held batch: {status} {held_reservation}"

    status, serial_genealogy = request(
        f"/api/v1/traceability/serials/{shipped_serial['serial_number']}", token=factory["access_token"],
    )
    assert status == 200, f"Finished serial traceability failed: {status} {serial_genealogy}"
    genealogy_source = next(
        (source for source in serial_genealogy.get("sources", []) if source["batch"]["id"] == flow_batch_id),
        None,
    )
    assert genealogy_source and genealogy_source.get("purchase_order", {}).get("po_number") == flow_po_number, (
        f"Serial genealogy lost its supplier purchase order: {serial_genealogy}"
    )
    assert genealogy_source.get("supplier", {}).get("name") == linked_flow_supplier["name"], (
        f"Serial genealogy lost its supplier: {genealogy_source}"
    )
    assert any(item.get("inspection_number") == final_inspection["inspection_number"] for item in genealogy_source.get("inspections", [])), (
        f"Serial genealogy lost the finished-product quality inspection: {genealogy_source}"
    )
    status, lot_genealogy = request(f"/api/v1/traceability/{flow_lot_number}", token=factory["access_token"])
    event_types = {event["event_type"] for event in lot_genealogy.get("events", [])} if status == 200 else set()
    movement_types = {movement["movement_type"] for movement in lot_genealogy.get("movements", [])} if status == 200 else set()
    assert status == 200 and {
        "GOODS_RECEIVED", "PRODUCTION_RESERVED", "PRODUCTION_CONSUMED",
        "FINISHED_SERIALS_CREATED", "QUALITY_PASS", "QUALITY_HOLD", "FINISHED_PRODUCT_SHIPPED",
        "FINISHED_QUALITY_HOLD", "FINISHED_QUALITY_RELEASED",
    } <= event_types, f"Lot genealogy is missing workflow events: HTTP {status} {event_types}"
    traced_finished_batch = next(
        (row for row in lot_genealogy.get("finished_product_batches", []) if row.get("id") == finished_batch["id"]),
        None,
    ) if status == 200 else None
    assert traced_finished_batch and {
        row.get("inspection_number") for row in traced_finished_batch.get("inspections", [])
    } >= {
        failed_finished_inspection["inspection_number"],
        passing_finished_inspection["inspection_number"],
    }, f"Forward lot trace omitted finished-product inspection history: {status} {lot_genealogy}"
    assert {"RECEIPT", "CONSUMPTION"} <= movement_types, f"Inventory genealogy is missing movements: {movement_types}"
    status, foreign_serial_trace = request(
        f"/api/v1/traceability/serials/{shipped_serial['serial_number']}",
        token=other_factory["access_token"],
    )
    assert status == 404, f"Cross-organisation serial genealogy was visible: {status} {foreign_serial_trace}"
    status, foreign_lot_trace = request(f"/api/v1/traceability/{flow_lot_number}", token=other_factory["access_token"])
    assert status == 404, f"Cross-organisation lot genealogy was visible: {status} {foreign_lot_trace}"

    status, refreshed = request("/api/v1/auth/refresh", method="POST", payload={"refresh_token": factory["refresh_token"]})
    assert status == 200 and refreshed.get("access_token"), f"Runtime role refresh-token update failed: {status} {refreshed}"

    status, language = request("/api/v1/auth/language", method="PATCH", payload={"language": "en"}, token=refreshed["access_token"])
    assert status == 200 and language.get("language") == "en", f"Runtime role user language update failed: {status} {language}"

    # The refresh and language endpoints commit; a subsequent read must retain
    # the request tenant context after SQLAlchemy opens another transaction.
    status, dashboard = request("/api/v1/dashboard", token=refreshed["access_token"])
    assert status == 200, f"Tenant context was not restored after commit: {status} {dashboard}"

    print("PostgreSQL runtime API acceptance passed: authentication and tenant isolation; supplier PO creation, invalid-state rejection, confirmation/dispatch and goods receipt; duplicate/over-quantity receipt rejection; live inventory; receiving/final inspection; insufficient-stock rejection; production reservation, consumption and serial generation; finished-batch/serial failure, quarantine, CAPA transition guard, controlled reinspection/release and forward/backward inspection genealogy; shipment, material hold/quarantine and held-stock rejection; supplier-to-PO-to-lot-to-production-to-serial genealogy; refresh rotation, language update, and post-commit tenant context.")


if __name__ == "__main__":
    main()
