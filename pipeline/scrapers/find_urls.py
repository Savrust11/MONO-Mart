"""
Find correct URLs for the 6 unconfirmed download pages by hovering over
the top-nav menus and capturing dropdown link hrefs.

Re-logs in between menu hovers to avoid session expiry.
"""
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Top-nav menus we want to expand
MENUS = ["商品管理", "物流管理", "在庫管理", "顧客・注文管理", "会計・精算",
         "分析", "ダッシュボード", "サイト管理", "マスター管理"]


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        locale="ja-JP",
        viewport={"width": 1440, "height": 900},
        http_credentials={
            "username": os.environ["ZOZO_BASIC_USER"],
            "password": os.environ["ZOZO_BASIC_PASSWORD"],
        },
    )
    page = ctx.new_page()

    print("=" * 70)
    print("Login...")
    login(page)
    print(f"Logged in: {page.url}")

    # Save the dashboard HTML for offline inspection
    dash_html = page.content()
    Path(__file__).parent.joinpath("html", "main_dashboard.html").write_text(dash_html, encoding="utf-8")

    print("\n=== All href values containing .asp ===")
    all_a = page.locator('a').all()
    seen = set()
    items_by_section: dict = {m: [] for m in MENUS}
    items_by_section["other"] = []

    for a in all_a:
        try:
            href = a.get_attribute("href") or ""
            text = (a.inner_text() or "").strip()
            if ".asp" not in href.lower():
                continue
            if href in seen:
                continue
            seen.add(href)
            # Get parent context
            try:
                parent_text = a.evaluate("el => el.closest('li, ul.dropdown, .menu')?.innerText || ''")
                parent_text = (parent_text or "")[:50]
            except Exception:
                parent_text = ""
            items_by_section["other"].append((text[:40], href, parent_text[:80]))
        except Exception:
            continue

    print(f"\nTotal unique .asp hrefs found: {len(seen)}")
    print(f"\nAll links (text → href):")
    for entry in items_by_section["other"]:
        print(f"   '{entry[0]:40s}' → {entry[1]}")

    # Try clicking each top menu to expand, then list submenu items
    print("\n\n" + "=" * 70)
    print("Expanding each top menu...")
    for menu in MENUS:
        print(f"\n--- {menu} ---")
        try:
            # Re-login if needed
            if "login" in page.url.lower() or "default.asp" in page.url.lower():
                login(page)
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20_000)
                time.sleep(1)

            # Hover the menu item
            menu_el = page.get_by_role("link", name=menu, exact=True).first
            if menu_el.count() > 0:
                menu_el.hover()
                time.sleep(0.6)
                # Find newly visible dropdown items
                dropdown_items = page.locator(".dropdown-menu a, .nav-dropdown a, ul.submenu a, .submenu a").all()
                for it in dropdown_items[:20]:
                    try:
                        text = (it.inner_text() or "").strip()
                        href = it.get_attribute("href") or ""
                        if text and href:
                            print(f"   '{text:40s}' → {href}")
                    except Exception:
                        pass

                # Take screenshot of expanded menu
                page.screenshot(path=str(SCREENSHOT_DIR / f"menu_{menu}.png"), full_page=False)
        except Exception as exc:
            print(f"   ERROR: {exc}")

    ctx.close()
    browser.close()

print(f"\n\nDone. Screenshots in {SCREENSHOT_DIR}")
