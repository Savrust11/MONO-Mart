"""
ZOZO バックオフィス ログインのドライラン (v2: 2-stage auth)

ZOZO バックオフィスは HTTP Basic Auth → Form Login の2段階認証が必要。

Usage:
  $env:ZOZO_BASIC_USER     = "<basic-user>"
  $env:ZOZO_BASIC_PASSWORD = "<basic-password>"
  $env:ZOZO_LOGIN_ID       = "<login-id>"
  $env:ZOZO_LOGIN_PASSWORD = "<login-password>"
  $env:HEADLESS            = "1"
  py -3.13 scrapers/test_login_dry_run.py
"""
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_URL    = "https://to.zozo.jp/to/"   # base path; login may live anywhere here
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

basic_user = os.environ.get("ZOZO_BASIC_USER", "")
basic_pw   = os.environ.get("ZOZO_BASIC_PASSWORD", "")
login_id   = os.environ.get("ZOZO_LOGIN_ID", "")
password   = os.environ.get("ZOZO_LOGIN_PASSWORD", "")
headless   = os.environ.get("HEADLESS", "1") == "1"

if not (basic_user and basic_pw):
    print("ERROR: set ZOZO_BASIC_USER / ZOZO_BASIC_PASSWORD env vars")
    sys.exit(1)

print(f"Basic Auth User : {basic_user}")
print(f"Basic Auth Pass : {'*' * len(basic_pw)}")
print(f"Login ID        : {login_id or '(not set — will skip form login)'}")
print(f"Login Password  : {'*' * len(password) if password else '(not set)'}")
print(f"Headless        : {headless}")
print()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=headless, slow_mo=200)

    # Pass HTTP Basic Auth credentials in context
    context = browser.new_context(
        locale="ja-JP",
        viewport={"width": 1440, "height": 900},
        http_credentials={"username": basic_user, "password": basic_pw},
    )
    page = context.new_page()

    try:
        # Step 1: open base URL with HTTP Basic Auth
        print("=" * 60)
        print("[1] Opening base URL with HTTP Basic Auth...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(2)
        page.screenshot(path=str(SCREENSHOT_DIR / "01_after_basic_auth.png"), full_page=True)
        print(f"   URL: {page.url}")
        print(f"   Title: {page.title()}")
        print(f"   Body length: {len(page.inner_text('body'))} chars")

        # Step 2: enumerate inputs
        print("\n[2] Detecting form inputs on the page...")
        inputs = page.locator("input").all()
        if not inputs:
            print("   No inputs found — may already be on a non-form page")
        for i, inp in enumerate(inputs[:20]):
            try:
                attr = {
                    "type":        inp.get_attribute("type"),
                    "name":        inp.get_attribute("name"),
                    "id":          inp.get_attribute("id"),
                    "placeholder": inp.get_attribute("placeholder"),
                }
                print(f"   input[{i}]: {attr}")
            except Exception as exc:
                print(f"   input[{i}]: error ({exc})")

        # Step 3: enumerate buttons / links
        print("\n[3] Detecting buttons + login-like links...")
        elements = page.locator('button, input[type="submit"], a').all()[:30]
        for i, el in enumerate(elements):
            try:
                text = (el.inner_text() or "").strip()[:50]
                href = el.get_attribute("href")
                if text or href:
                    print(f"   [{i}]: text='{text}' href={href}")
            except Exception:
                pass

        # Step 4: try form login if credentials provided
        if login_id and password:
            print("\n[4] Attempting form login...")
            login_filled = False
            for sel in ['input[name="login_id"]', 'input[name="loginId"]', 'input[name="id"]',
                        'input[name="user_id"]', 'input[name="email"]', 'input[name="userid"]',
                        'input[type="email"]', 'input[type="text"]:visible']:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, login_id, timeout=3_000)
                        print(f"   Filled login_id using: {sel}")
                        login_filled = True
                        break
                except Exception:
                    continue

            pw_filled = False
            for sel in ['input[name="password"]', 'input[name="pw"]', 'input[type="password"]']:
                try:
                    if page.locator(sel).count() > 0:
                        page.fill(sel, password, timeout=3_000)
                        print(f"   Filled password using: {sel}")
                        pw_filled = True
                        break
                except Exception:
                    continue

            if not (login_filled and pw_filled):
                print(f"   WARN: login_filled={login_filled}, pw_filled={pw_filled}")
            else:
                page.screenshot(path=str(SCREENSHOT_DIR / "02_filled_form.png"), full_page=True)

                # Click submit
                clicked = False
                for sel in ['button[type="submit"]', 'input[type="submit"]',
                            'button:has-text("ログイン")', 'a:has-text("ログイン")',
                            'button:has-text("Login")', 'button:has-text("login")']:
                    try:
                        if page.locator(sel).count() > 0:
                            page.click(sel, timeout=3_000)
                            print(f"   Clicked submit using: {sel}")
                            clicked = True
                            break
                    except Exception:
                        continue

                if not clicked:
                    print("   WARN: could not find submit button")

                # Wait and report
                time.sleep(5)
                print(f"   New URL: {page.url}")
                print(f"   New Title: {page.title()}")
                page.screenshot(path=str(SCREENSHOT_DIR / "03_after_login.png"), full_page=True)

                if "login" not in page.url.lower():
                    print("   ✓ Logged in successfully")
                else:
                    print("   ✗ Still on login page")

    finally:
        context.close()
        browser.close()
        print("\nDone. Screenshots saved in:")
        print(f"   {SCREENSHOT_DIR}")
