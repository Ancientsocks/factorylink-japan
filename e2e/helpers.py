from playwright.sync_api import Page


def sign_in(page: Page, email: str, password: str = "FactoryLink2026!") -> None:
    page.locator(".login-language select").select_option("en")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Sign in", exact=True).click()
    page.locator(".app-shell").wait_for(state="visible")
    page.locator(".topbar .locale-select select").select_option("en")
    page.wait_for_timeout(200)


def nav_button(page: Page, label: str):
    """Resolve a navigation item without colliding with page-level action buttons."""
    return page.locator(".main-nav").get_by_role("button", name=label, exact=True)
