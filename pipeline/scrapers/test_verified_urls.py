"""Test the newly-verified direct CSV download URLs."""
import os
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"

# Direct CSV endpoints discovered by menu hovering
TARGETS = [
    ("orders",        "https://to.zozo.jp/to/order_csv.asp?c=Order_CSV"),
    ("inventory_sku", "https://to.zozo.jp/to/zaiko_csv2.asp?c=Zaiko"),
    ("sale_settings", "https://to.zozo.jp/to/Sales_download.asp"),
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

    print("Login...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
    page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
    with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
        page.get_by_role("button", name="ログイン").first.click()
    print(f"OK: {page.url}")

    for name, url in TARGETS:
        print(f"\n--- Testing {name}: {url}")
        try:
            resp = ctx.request.get(url, timeout=120_000)
            ct = resp.headers.get("content-type", "")
            cd = resp.headers.get("content-disposition", "")
            body = resp.body()
            head = body[:300]
            print(f"   status={resp.status}  content-type={ct}  size={len(body):,} bytes")
            print(f"   content-disposition={cd}")
            if b"<html" in head.lower() or b"<!doctype" in head.lower():
                print(f"   ⚠ HTML response (not CSV)")
                print(f"   First 200 chars: {head[:200].decode('utf-8', errors='replace')}")
            else:
                # Looks like CSV — show first row
                first_line = body[:500].split(b"\n")[0]
                # Try cp932 first, fallback to utf-8
                for enc in ("cp932", "utf-8", "shift_jis"):
                    try:
                        decoded = first_line.decode(enc).strip()
                        print(f"   ✓ Decoded ({enc}): {decoded[:200]}")
                        break
                    except UnicodeDecodeError:
                        continue
        except Exception as exc:
            print(f"   ✗ Error: {exc}")

    ctx.close()
    browser.close()

print("\nDone")
