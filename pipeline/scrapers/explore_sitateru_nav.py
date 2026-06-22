# -*- coding: utf-8 -*-
"""
Final exploration: click export link, capture ALL network activity,
look for download URL pattern or polling endpoint.
Also check if the export triggers immediately for small result sets.
"""
import sys, json, time, urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright

SESS = Path(__file__).parent / "sessions"
STATE_FILE = str(SESS / "sitateru_state.json")
sys.stdout.reconfigure(encoding="utf-8")
ITEMS_URL = "https://direct.sitateru.com/sewing/brand/productions"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)
    ctx = browser.new_context(storage_state=STATE_FILE, locale="ja-JP", accept_downloads=True)
    page = ctx.new_page()

    # Capture ALL network activity
    all_requests = []
    all_responses = []
    def on_req(r):
        all_requests.append({"method": r.method, "url": r.url, "type": r.resource_type})
    def on_resp(r):
        ct = r.headers.get("content-type","")
        cd = r.headers.get("content-disposition","")
        loc = r.headers.get("location","")
        all_responses.append({"status": r.status, "ct": ct, "cd": cd, "loc": loc, "url": r.url})
    page.on("request", on_req)
    page.on("response", on_resp)

    # Search with small result (15 items)
    kw = "プロダクト1部 26/SS 進行中"
    url = ITEMS_URL + "?keyword=" + urllib.parse.quote(kw) + "&sort_priority=updated_at&sort_desc=desc&archive_mode=&button="
    page.goto(url, timeout=30_000, wait_until="networkidle")
    time.sleep(3)
    all_requests.clear(); all_responses.clear()

    # Click the SKU export button
    page.evaluate("window.scrollTo(0, 0)")
    page.locator("div.menu-toggle").first.click()
    time.sleep(1)
    page.locator("a[data-target='import-sku']").first.click()
    time.sleep(2)

    # Click export link with download interception
    export_link = page.locator("a[href*='stock_keeping_units/export']").first
    href = export_link.get_attribute("href")
    print(f"Export URL: {href}")

    try:
        with page.expect_download(timeout=30_000) as dl_info:
            export_link.click()
            time.sleep(10)  # wait up to 10s after click
        dl = dl_info.value
        print(f"DOWNLOAD TRIGGERED: {dl.suggested_filename!r}  url={dl.url!r}")
        out = SESS / "test_export_sku.csv"
        dl.save_as(str(out))
        print(f"Saved: {out}")
    except Exception as e:
        print(f"No download in 30s: {str(e)[:80]}")

    page.screenshot(path=str(SESS / "export_after_click.png"))
    print(f"URL after click: {page.url}")

    # Show all network activity during/after click
    print("\n=== ALL REQUESTS AFTER EXPORT CLICK ===")
    for r in all_requests:
        if r["type"] in ("xhr","fetch","document"):
            print(f"  {r['method']} [{r['type']}] {r['url'][:100]}")

    print("\n=== ALL RESPONSES WITH CONTENT-DISPOSITION OR CSV ===")
    for r in all_responses:
        if r["cd"] or "csv" in r["ct"].lower() or r["status"] in (302,301):
            print(f"  {r['status']} ct={r['ct'][:30]!r} cd={r['cd']!r} loc={r['loc'][:60]!r}")
            print(f"       url={r['url'][:100]}")

    # Check the productions/export URL directly (maybe different from SKU export)
    print("\n=== TRYING productions/export DIRECTLY ===")
    all_requests.clear(); all_responses.clear()
    page.keyboard.press("Escape")  # close modal
    time.sleep(1)
    prod_export_link = page.locator("a[href*='productions/export']").first
    if prod_export_link.count() > 0:
        href2 = prod_export_link.get_attribute("href")
        print(f"Productions export URL: {href2}")
        try:
            with page.expect_download(timeout=20_000) as dl_info2:
                prod_export_link.click()
                time.sleep(8)
            dl2 = dl_info2.value
            print(f"DOWNLOAD: {dl2.suggested_filename!r}")
        except Exception as e:
            print(f"No download: {str(e)[:80]}")
    else:
        print("productions/export link not visible (modal closed)")

    browser.close()
