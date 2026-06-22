"""Test downloading SaleSetting CSV. Multiple strategies attempted."""
import os
import time
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
TARGET_PAGE = "https://to.zozo.jp/to/SaleSetting.asp"
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)


def do_login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
    page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
    with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
        page.get_by_role("button", name="ログイン").first.click()


with tempfile.TemporaryDirectory() as tmpdir:
    download_dir = Path(tmpdir)

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

        print("[1] Login + navigate to SaleSetting...")
        do_login(page)
        page.goto(TARGET_PAGE, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(2)
        print(f"   URL: {page.url}")

        print("\n[2] Inspect link HTML + parent dropdown structure...")
        link_html = page.locator("a.dropdown-link[href='Sales_download.asp']").first.evaluate("el => el.outerHTML")
        print(f"   Link HTML: {link_html}")
        parent_html = page.locator("a.dropdown-link[href='Sales_download.asp']").first.evaluate(
            "el => el.parentElement.outerHTML"
        )
        print(f"   Parent HTML (first 800 chars):")
        print(f"   {parent_html[:800]}")

        # Save full page HTML for offline inspection
        full_html = page.content()
        html_file = SCREENSHOT_DIR / "sale_setting_full.html"
        html_file.write_text(full_html, encoding="utf-8")
        print(f"\n   Full page HTML saved: {html_file}")

        print("\n[3] Try: Get full download URL and navigate directly with cookie...")
        # Strategy: read existing cookies, then issue GET on Sales_download.asp via fetch
        # If the page sets up state with POST first, this won't work — but worth trying
        try:
            with page.expect_download(timeout=60_000) as dl_info:
                # Just click — but use no_wait_after to skip navigation wait
                page.locator("a.dropdown-link[href='Sales_download.asp']").first.click(
                    force=True, no_wait_after=True, timeout=5_000,
                )
            download = dl_info.value
            fn = download.suggested_filename or "salegoods.csv"
            local_path = download_dir / fn
            download.save_as(local_path)
            print(f"   ✓ Downloaded: {fn} ({local_path.stat().st_size:,} bytes)")

            print("\n[4] Upload to GCS...")
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(os.environ.get("GCS_RAW_BUCKET", "mono-back-office-system-raw-data"))
            gcs_path = f"uploads/zozo/sale/2026-05-12/{fn}"
            bucket.blob(gcs_path).upload_from_filename(str(local_path))
            print(f"   ✓ Uploaded: gs://{bucket.name}/{gcs_path}")

            print("\n[5] First 300 bytes of CSV:")
            print("   ", local_path.read_bytes()[:300])
        except Exception as exc:
            print(f"   ✗ Click+download failed: {exc}")

        ctx.close()
        browser.close()

print("\nDone")
