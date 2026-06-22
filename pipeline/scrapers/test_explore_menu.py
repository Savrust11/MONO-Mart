"""
Logged-in exploration: find the URLs for each download page.
Saves screenshots and the full HTML for offline inspection.
"""
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
HTML_DIR = Path(__file__).parent / "html"
SCREENSHOT_DIR.mkdir(exist_ok=True)
HTML_DIR.mkdir(exist_ok=True)

# Menu paths to explore (label → click sequence)
EXPLORE = [
    "分析",          # → expect submenu with 注文, 在庫, etc.
    "商品管理",       # → expect submenu with 予約管理, セール設定, etc.
    "サイト管理",     # → expect ZOZOAD, etc.
    "ダッシュボード",  # → expect 商品別実績(新), etc.
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        locale="ja-JP",
        viewport={"width": 1440, "height": 900},
        accept_downloads=True,
        http_credentials={
            "username": os.environ["ZOZO_BASIC_USER"],
            "password": os.environ["ZOZO_BASIC_PASSWORD"],
        },
    )
    page = ctx.new_page()

    print("[1] Login...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
    page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
    with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
        page.get_by_role("button", name="ログイン").first.click()
    print(f"   Logged in: {page.url}")
    page.screenshot(path=str(SCREENSHOT_DIR / "30_dashboard.png"), full_page=True)

    # Get all top-level nav items
    print("\n[2] Top-level nav items found:")
    nav_links = page.locator("nav a, .nav a, header a, .menu a, ul.global a").all()
    seen = set()
    for el in nav_links[:40]:
        try:
            text = (el.inner_text() or "").strip()
            href = el.get_attribute("href")
            if text and href and href not in seen:
                seen.add(href)
                print(f"   {text:30s} → {href}")
        except Exception:
            pass

    # Save full HTML of the dashboard for offline inspection
    html_path = HTML_DIR / "dashboard.html"
    html_path.write_text(page.content(), encoding="utf-8")
    print(f"\n   Full HTML saved: {html_path}")

    # Try to enumerate all <a> tags with href
    print("\n[3] All anchors with /to/ paths:")
    all_anchors = page.locator('a[href*="/to/"]').all()
    seen_full = set()
    for a in all_anchors[:80]:
        try:
            text = (a.inner_text() or "").strip()[:40]
            href = a.get_attribute("href")
            if href and href not in seen_full:
                seen_full.add(href)
                print(f"   '{text}' → {href}")
        except Exception:
            pass

    # Hover/click each menu and check what unfolds
    for label in EXPLORE:
        print(f"\n[4] Exploring '{label}'...")
        try:
            menu_item = page.get_by_text(label, exact=True).first
            menu_item.hover()
            time.sleep(1)
            page.screenshot(path=str(SCREENSHOT_DIR / f"40_hover_{label}.png"))

            # Try clicking
            with page.expect_navigation(wait_until="domcontentloaded", timeout=10_000):
                menu_item.click()
            print(f"   '{label}' navigated to: {page.url}")
            page.screenshot(path=str(SCREENSHOT_DIR / f"41_click_{label}.png"), full_page=True)

            # List submenu items found
            sub_links = page.locator('a[href*="/to/"]').all()[:20]
            for s in sub_links:
                try:
                    text = (s.inner_text() or "").strip()[:30]
                    href = s.get_attribute("href")
                    if text:
                        print(f"      sub: '{text}' → {href}")
                except Exception:
                    pass

            # Go back
            page.goto(LOGIN_URL.replace("/to/", "/to/main.asp"), wait_until="domcontentloaded", timeout=15_000)
        except Exception as exc:
            print(f"   ERROR exploring '{label}': {exc}")

    ctx.close()
    browser.close()

print(f"\nScreenshots in {SCREENSHOT_DIR}")
print(f"HTML in {HTML_DIR}")
