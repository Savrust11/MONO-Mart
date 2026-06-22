"""Try fetching the CSV directly using session cookies (bypasses dropdown UI)."""
import os
import time
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
DOWNLOAD_URLS = {
    "sale_settings": "https://to.zozo.jp/to/Sales_download.asp",
}

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

        # Login
        print("[1] Login...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()
        print(f"   OK: {page.url}")

        # Visit SaleSetting page first to set up session state
        print("\n[2] Visit SaleSetting.asp (sets up session)...")
        page.goto("https://to.zozo.jp/to/SaleSetting.asp", wait_until="domcontentloaded", timeout=30_000)
        time.sleep(2)
        print(f"   OK: {page.url}")

        # Now use the context's APIRequestContext to fetch the download URL
        # This reuses the browser's session cookies
        print("\n[3] Fetch Sales_download.asp via APIRequestContext...")
        for name, url in DOWNLOAD_URLS.items():
            try:
                resp = ctx.request.get(url, timeout=60_000)
                print(f"   {name}: status={resp.status}, content-type={resp.headers.get('content-type')}, size={len(resp.body())} bytes")
                if resp.status == 200:
                    # Save body
                    cd = resp.headers.get("content-disposition", "")
                    fn = "salegoods.csv"
                    if "filename=" in cd:
                        fn = cd.split("filename=")[-1].strip('"; ')
                    local_path = download_dir / fn
                    local_path.write_bytes(resp.body())
                    print(f"   ✓ Saved: {fn} ({local_path.stat().st_size:,} bytes)")
                    print(f"   First 300 bytes: {local_path.read_bytes()[:300]!r}")

                    # Upload to GCS
                    from google.cloud import storage
                    client = storage.Client()
                    bucket = client.bucket(os.environ.get("GCS_RAW_BUCKET", "mono-back-office-system-raw-data"))
                    gcs_path = f"uploads/zozo/sale/2026-05-12/{fn}"
                    bucket.blob(gcs_path).upload_from_filename(str(local_path))
                    print(f"   ✓ Uploaded: gs://{bucket.name}/{gcs_path}")
            except Exception as exc:
                print(f"   ✗ {name}: {exc}")

        ctx.close()
        browser.close()

print("\nDone")
