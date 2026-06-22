"""
ZOZO Back Office full login test (stage 1 + stage 2).

  Stage 1: HTTP Basic Auth (proxy/CDN) — handled by http_credentials
  Stage 2: HTML form login on the ZOZO BACK OFFICE page
"""
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

BASIC_USER = os.environ.get("ZOZO_BASIC_USER",     "<ZOZO_BASIC_USER>")
BASIC_PW   = os.environ.get("ZOZO_BASIC_PASSWORD", "<ZOZO_BASIC_PASSWORD>")
FORM_USER  = os.environ.get("ZOZO_LOGIN_ID",       "<ZOZO_LOGIN_ID>")
FORM_PW    = os.environ.get("ZOZO_LOGIN_PASSWORD", "<ZOZO_LOGIN_PASSWORD>")

print(f"Stage 1 (Basic Auth): {BASIC_USER}")
print(f"Stage 2 (Form login): {FORM_USER}")
print()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        locale="ja-JP",
        viewport={"width": 1280, "height": 800},
        http_credentials={"username": BASIC_USER, "password": BASIC_PW},
        accept_downloads=True,
    )
    page = ctx.new_page()

    try:
        # ── Stage 1 ──
        print("=" * 60)
        print("[1] Loading login page (Basic Auth)...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20_000)
        time.sleep(1)
        print(f"   URL: {page.url}")
        print(f"   Title: {page.title()}")
        page.screenshot(path=str(SCREENSHOT_DIR / "20_basic_passed.png"), full_page=True)

        # ── Inspect form ──
        print("\n[2] Inspecting login form...")
        inputs = page.locator("input").all()
        print(f"   Found {len(inputs)} input(s):")
        for i, inp in enumerate(inputs):
            attr = {
                "type":        inp.get_attribute("type"),
                "name":        inp.get_attribute("name"),
                "id":          inp.get_attribute("id"),
                "placeholder": inp.get_attribute("placeholder"),
            }
            print(f"      [{i}]: {attr}")

        forms = page.locator("form").all()
        print(f"   Found {len(forms)} form(s):")
        for i, f in enumerate(forms):
            print(f"      form[{i}] action={f.get_attribute('action')} method={f.get_attribute('method')}")

        buttons = page.locator("button, input[type='submit'], input[type='button']").all()
        print(f"   Found {len(buttons)} button(s):")
        for i, b in enumerate(buttons[:10]):
            text = (b.inner_text() or b.get_attribute("value") or "").strip()[:40]
            print(f"      button[{i}]: text='{text}' type={b.get_attribute('type')}")

        # ── Stage 2: form login ──
        print("\n[3] Filling form...")
        login_filled = False
        for sel in ['input[name="LoginName"]', 'input#UserID',
                    'input[name="login_id"]', 'input[name="loginId"]', 'input[name="id"]',
                    'input[name="user_id"]', 'input[name="userid"]', 'input[name="email"]']:
            try:
                if page.locator(sel).count() > 0:
                    page.fill(sel, FORM_USER, timeout=3_000)
                    print(f"   Filled login_id with: {sel}")
                    login_filled = True
                    break
            except Exception:
                continue

        pw_filled = False
        for sel in ['input[name="Password"]', 'input[name="password"]', 'input[name="pw"]', 'input[type="password"]']:
            try:
                if page.locator(sel).count() > 0:
                    page.fill(sel, FORM_PW, timeout=3_000)
                    print(f"   Filled password with: {sel}")
                    pw_filled = True
                    break
            except Exception:
                continue

        page.screenshot(path=str(SCREENSHOT_DIR / "21_form_filled.png"), full_page=True)

        if login_filled and pw_filled:
            print("\n[4] Submitting form (with navigation wait)...")
            submitted = False
            try:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
                    page.get_by_role("button", name="ログイン").first.click()
                print("   Click + navigation completed")
                submitted = True
            except Exception as exc:
                print(f"   Submit/navigation failed: {exc}")
                # Even if expect_navigation timed out, the page may have changed
                submitted = page.url != LOGIN_URL

            if submitted:
                time.sleep(5)
                print(f"\n[5] After submit:")
                print(f"   URL: {page.url}")
                print(f"   Title: {page.title()}")
                page.screenshot(path=str(SCREENSHOT_DIR / "22_logged_in.png"), full_page=True)

                if "login" not in page.url.lower():
                    print("   ✓ LOGGED IN successfully!")
                    body = page.inner_text("body")[:300].replace("\n", " ")
                    print(f"   First 300 chars of page: {body}")
                else:
                    print("   ✗ Still on login page — login failed")
                    body = page.inner_text("body")[:200].replace("\n", " ")
                    print(f"   Page content: {body}")
            else:
                print("   ✗ Could not find submit button")
        else:
            print(f"\n   ✗ Form fill failed (login_filled={login_filled}, pw_filled={pw_filled})")
    finally:
        ctx.close()
        browser.close()
        print("\nDone — screenshots in", SCREENSHOT_DIR)
