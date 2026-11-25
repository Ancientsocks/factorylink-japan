from __future__ import annotations

import re
import time

from playwright.sync_api import expect

from helpers import nav_button, sign_in


def test_factory_admin_can_navigate_modules_switch_japanese_and_export(page):
    sign_in(page, "admin@factorylink.jp")
    expect(page.get_by_role("heading", name="Dashboard", exact=True)).to_be_visible()
    expect(page.get_by_text("Sakura Precision Manufacturing", exact=True)).to_be_visible()

    for label in ("Production", "Inventory", "Suppliers", "Purchase Orders", "Quality", "Traceability", "Maintenance", "Reports"):
        expect(nav_button(page, label)).to_be_visible()

    nav_button(page, "Production").click()
    expect(page.get_by_role("heading", name="Production", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="New production order")).to_be_visible()

    page.locator(".topbar .locale-select select").select_option("ja")
    expect(page.get_by_role("heading", name="生産管理", exact=True)).to_be_visible()
    page.locator(".topbar .locale-select select").select_option("en")
    expect(page.get_by_role("heading", name="Production", exact=True)).to_be_visible()

    nav_button(page, "Reports").click()
    expect(page.get_by_role("heading", name="Reports", exact=True)).to_be_visible()
    with page.expect_download() as download_info:
        page.locator(".report-card").first.get_by_role("button", name="CSV", exact=True).click()
    download = download_info.value
    assert download.suggested_filename.endswith(".csv")


def test_supplier_portal_exposes_only_supplier_modules(page):
    sign_in(page, "supplier@osaka-parts.jp")
    expect(page.get_by_role("heading", name="Supplier portal", exact=True)).to_be_visible()
    expect(nav_button(page, "Purchase Orders")).to_be_visible()
    expect(nav_button(page, "Documents")).to_be_visible()
    for forbidden in ("Production", "Inventory", "Quality", "Traceability", "Maintenance", "Reports", "Audit trail", "Users & Access"):
        expect(nav_button(page, forbidden)).to_have_count(0)

    nav_button(page, "Purchase Orders").click()
    expect(page.get_by_role("heading", name="Purchase Orders", exact=True)).to_be_visible()
    expect(page.get_by_text("PO-2026-001", exact=True)).to_be_visible()


def test_factory_supplier_receipt_quality_and_traceability_workflow(app_server, browser_context):
    suffix = str(int(time.time()))
    po_number = f"E2E-{suffix}"
    lot_number = f"E2E-LOT-{suffix}"

    # Manufacturer creates a purchase order and submits it to the supplier.
    factory = browser_context.new_page()
    factory.goto(app_server["base_url"])
    sign_in(factory, "admin@factorylink.jp")
    nav_button(factory, "Purchase Orders").click()
    factory.get_by_role("button", name="New purchase order").click()
    supplier_option = factory.get_by_label("Suppliers").locator("option", has_text="Osaka Parts Supply")
    expect(supplier_option).to_have_count(1)
    factory.get_by_label("Suppliers").select_option(label="Osaka Parts Supply")
    factory.get_by_label("Order number").fill(po_number)
    factory.get_by_label("Item").fill("E2E Precision Steel")
    factory.get_by_label("Quantity").fill("40")
    factory.get_by_label("Unit", exact=True).fill("kg")
    factory.get_by_label("Unit price (JPY)").fill("125")
    invalid_fields = factory.locator(".modal-card form").evaluate(
        "(form) => Array.from(form.elements).filter((field) => !field.checkValidity()).map((field) => ({"
        "label: field.labels?.[0]?.textContent, value: field.value, message: field.validationMessage"
        "}))"
    )
    assert not invalid_fields, f"Purchase-order form has invalid fields: {invalid_fields}"
    with factory.expect_response(
        lambda response: response.url.endswith("/api/v1/purchase-orders")
        and response.request.method == "POST"
    ) as create_response:
        factory.locator(".modal-card").get_by_role("button", name="Save").click()
    assert create_response.value.status == 201, create_response.value.text()

    order_row = factory.get_by_role("row").filter(has_text=po_number)
    expect(order_row).to_be_visible()
    order_row.get_by_role("button", name="Advance").click()
    expect(order_row.get_by_text("Submitted", exact=True)).to_be_visible()

    # Supplier confirms and dispatches the exact shared purchase order.
    supplier = browser_context.new_page()
    supplier.goto(app_server["base_url"])
    sign_in(supplier, "supplier@osaka-parts.jp")
    nav_button(supplier, "Purchase Orders").click()
    supplier_row = supplier.get_by_role("row").filter(has_text=po_number)
    expect(supplier_row).to_be_visible()
    supplier_row.get_by_role("button", name="Confirm", exact=True).click()
    expect(supplier_row.get_by_text("Confirmed", exact=True)).to_be_visible()
    supplier_row.get_by_role("button", name="Advance", exact=True).click()
    expect(supplier_row.get_by_text("In Transit", exact=True)).to_be_visible()

    # Warehouse receives a partial quantity against that purchase order.
    warehouse = browser_context.new_page()
    warehouse.goto(app_server["base_url"])
    sign_in(warehouse, "warehouse@factorylink.jp")
    nav_button(warehouse, "Inventory").click()
    warehouse.get_by_role("button", name="Receive material").click()
    po_option = warehouse.locator(".modal-card select option").filter(has_text=po_number)
    expect(po_option).to_have_count(1)
    po_id = po_option.get_attribute("value")
    assert po_id, "The in-transit purchase order must be available for goods receipt"
    warehouse.get_by_label("Link to purchase order (optional)").select_option(po_id)
    warehouse.get_by_label("Material", exact=True).fill("E2E Precision Steel")
    warehouse.get_by_label("Lot number").fill(lot_number)
    warehouse.get_by_label("Quantity", exact=True).fill("10")
    warehouse.get_by_label("Unit", exact=True).fill("kg")
    warehouse.get_by_label("Receipt reference").fill(f"GR-{suffix}")
    warehouse.locator(".modal-card").get_by_role("button", name="Save").click()
    expect(warehouse.get_by_text(lot_number, exact=True)).to_be_visible()

    # Factory reloads its existing view to fetch the other user's newly recorded receipt.
    factory.reload()
    factory.locator(".app-shell").wait_for(state="visible")
    nav_button(factory, "Purchase Orders").click()
    expect(factory.get_by_text(re.compile(r"Received\s+10\s+·\s+Remaining\s+30"))).to_be_visible()

    # Quality records a failure; traceability must show the batch on hold.
    quality = browser_context.new_page()
    quality.goto(app_server["base_url"])
    sign_in(quality, "quality@factorylink.jp")
    nav_button(quality, "Quality").click()
    quality.get_by_role("button", name="New inspection").click()
    quality.get_by_label("Inspection number").fill(f"QI-{suffix}")
    quality.get_by_role("textbox", name="Product").fill("E2E Precision Part")
    batch_option = quality.locator(".modal-card select option").filter(has_text=lot_number)
    expect(batch_option).to_have_count(1)
    batch_id = batch_option.get_attribute("value")
    assert batch_id, "The newly received batch must be selectable for inspection"
    quality.locator(".modal-card select").nth(0).select_option(batch_id)
    quality.get_by_label("Result").select_option("FAIL")
    quality.get_by_label("Defects").fill("1")
    quality.get_by_label("Units inspected").fill("10")
    quality.locator(".modal-card").get_by_role("textbox", name="Corrective action").fill(
        "Quarantine the lot and investigate the process"
    )
    with quality.expect_response(
        lambda response: response.url.endswith("/api/v1/quality/inspections")
        and response.request.method == "POST"
    ) as inspection_response:
        quality.locator(".modal-card").get_by_role("button", name="Save").click()
    assert inspection_response.value.status == 201, inspection_response.value.text()
    expect(quality.get_by_text(f"QI-{suffix}", exact=True)).to_be_visible()

    nav_button(quality, "Traceability").click()
    quality.get_by_placeholder("LOT-8831").fill(lot_number)
    quality.get_by_role("button", name="Search", exact=True).click()
    expect(quality.get_by_text("Hold", exact=True)).to_be_visible()
    expect(quality.get_by_text("Quality Hold", exact=True)).to_be_visible()


def test_password_recovery_action_link_can_be_completed(page):
    page.locator(".login-language select").select_option("en")
    page.get_by_role("button", name="Forgot password?", exact=True).click()
    page.get_by_label("Email").fill("maintenance@factorylink.jp")
    page.get_by_role("button", name="Send reset link", exact=True).click()
    reset_link = page.get_by_role("link", name="Open development reset link", exact=True)
    expect(reset_link).to_be_visible()
    href = reset_link.get_attribute("href")
    assert href and "action=password-reset" in href
    page.goto(href)
    page.get_by_label("Password", exact=True).fill("E2E-Updated-Password-2026!")
    page.get_by_label("Confirm password").fill("E2E-Updated-Password-2026!")
    page.get_by_role("button", name="Update password", exact=True).click()
    expect(page.get_by_text("Password updated. Please sign in with your new password.", exact=True)).to_be_visible()
    page.get_by_label("Email").fill("maintenance@factorylink.jp")
    page.get_by_label("Password").fill("E2E-Updated-Password-2026!")
    page.get_by_role("button", name="Sign in", exact=True).click()
    expect(page.locator(".app-shell")).to_be_visible()


def test_user_invitation_activates_account_with_assigned_role(page, app_server):
    sign_in(page, "admin@factorylink.jp")
    nav_button(page, "Users & Access").click()
    expect(page.get_by_role("heading", name="Users & Access", level=1, exact=True)).to_be_visible()
    page.get_by_role("button", name="Invite user", exact=True).click()
    email = f"browser-invite-{int(time.time())}@factorylink-e2e.jp"
    page.get_by_label("Name").fill("Browser E2E Operator")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Role").select_option("PRODUCTION_MANAGER")
    page.locator(".modal-card").get_by_label("Language").select_option("en")
    with page.expect_response(
        lambda response: response.url.endswith("/api/v1/users/invitations")
        and response.request.method == "POST"
    ) as invitation_response:
        page.locator(".modal-card").get_by_role("button", name="Save").click()
    assert invitation_response.value.status == 202, invitation_response.value.text()

    invitation_link = page.get_by_role("link", name="Open invitation link", exact=True)
    expect(invitation_link).to_be_visible()
    href = invitation_link.get_attribute("href")
    assert href and "action=accept-invitation" in href

    page.evaluate("sessionStorage.clear()")
    page.goto(href)
    expect(page.get_by_role("heading", name="Accept your invitation", exact=True)).to_be_visible()
    page.get_by_label("Password", exact=True).fill("Browser-Invite-Password-2026!")
    page.get_by_label("Confirm password").fill("Browser-Invite-Password-2026!")
    page.get_by_role("button", name="Activate account", exact=True).click()
    page.locator(".app-shell").wait_for(state="visible")
    page.locator(".topbar .locale-select select").select_option("en")
    expect(nav_button(page, "Production")).to_be_visible()
    expect(nav_button(page, "Users & Access")).to_have_count(0)
