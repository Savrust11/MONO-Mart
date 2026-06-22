"""
Explore all 9 ZOZO download pages to discover the actual download URLs/forms.

For each page:
  - Visit the page URL
  - Save HTML for offline inspection
  - Extract all <a href> in dropdowns
  - Extract all <form> elements (action + method)
  - Try fetching the download URL via session cookies
  - Report: was it CSV (binary) or HTML (intermediate page)
"""
import os
import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
HTML_DIR = Path(__file__).parent / "html"
HTML_DIR.mkdir(exist_ok=True)

# 9 pages to explore — discovered from earlier exploration + standard ZOZO menu structure
PAGES = [
    {"name": "orders",         "page": "Order.asp?c=Init",                    "label": "受注 (No.1)"},
    {"name": "shipped",        "page": "Send.asp?c=Init",                     "label": "発送 (No.2)"},
    {"name": "reservations",   "page": "Reserve.asp?c=ReserveList",           "label": "予約管理一覧 (No.3)"},
    {"name": "inventory_sku",  "page": "StockBySKU.asp?c=Init",               "label": "倉庫在庫 SKU毎 (No.4)"},
    {"name": "stock_analysis", "page": "StockAnalysis.asp?c=Init",            "label": "在庫分析 (No.6)"},
    {"name": "zozoad",         "page": "Advertisement.asp",                   "label": "ZOZOAD (No.7)"},
    {"name": "performance",    "page": "GoodsResult.asp",                     "label": "商品別実績(新) (No.8)"},
    {"name": "product_master", "page": "GoodsSearch.asp?c=Init",              "label": "登録商品 (No.9)"},
    {"name": "sale_settings",  "page": "SaleSetting.asp",                     "label": "セール設定 (No.17)"},
]

results = []

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

    print("=" * 70)
    print("Login...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
    page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
    with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
        page.get_by_role("button", name="ログイン").first.click()
    print(f"Logged in: {page.url}")

    for cfg in PAGES:
        result = {"name": cfg["name"], "label": cfg["label"], "page": cfg["page"]}
        print(f"\n{'─' * 70}")
        print(f"[{cfg['name']}] {cfg['label']}")
        print(f"   URL: https://to.zozo.jp/to/{cfg['page']}")

        try:
            resp = page.goto(f"https://to.zozo.jp/to/{cfg['page']}",
                             wait_until="domcontentloaded", timeout=30_000)
            time.sleep(1.5)
            result["status"] = resp.status if resp else 0
            result["final_url"] = page.url
            result["title"] = page.title()
            print(f"   status={result['status']}  title={result['title']}")

            # Save HTML
            html_file = HTML_DIR / f"{cfg['name']}.html"
            html_file.write_text(page.content(), encoding="utf-8")
            result["html_file"] = str(html_file.name)
            result["html_size"] = html_file.stat().st_size
            print(f"   HTML saved: {html_file.name} ({result['html_size']:,} bytes)")

            # Find download links
            download_links = []
            for a in page.locator("a").all()[:200]:
                try:
                    text = (a.inner_text() or "").strip()
                    href = a.get_attribute("href") or ""
                    if any(kw in text for kw in ["ダウンロード", "CSV", "Download", "download"]):
                        download_links.append({"text": text[:50], "href": href})
                    elif any(kw in href.lower() for kw in ["download", "csv", "_dl", "export"]):
                        download_links.append({"text": text[:50], "href": href})
                except Exception:
                    continue
            # Also check buttons
            for btn in page.locator("button, input[type='submit']").all()[:30]:
                try:
                    text = (btn.inner_text() or btn.get_attribute("value") or "").strip()
                    if any(kw in text for kw in ["ダウンロード", "CSV", "Download"]):
                        download_links.append({"text": text[:50], "href": "(button/submit)"})
                except Exception:
                    continue

            result["download_links"] = download_links
            print(f"   download links found: {len(download_links)}")
            for dl in download_links[:5]:
                print(f"      - '{dl['text']}' → {dl['href']}")

            # Find forms
            forms = []
            for f in page.locator("form").all()[:10]:
                try:
                    forms.append({
                        "action": f.get_attribute("action") or "",
                        "method": f.get_attribute("method") or "GET",
                    })
                except Exception:
                    continue
            result["forms"] = forms
            print(f"   forms: {len(forms)}")

        except Exception as exc:
            result["error"] = str(exc)
            print(f"   ERROR: {exc}")

        results.append(result)
        time.sleep(0.5)

    ctx.close()
    browser.close()

# Write summary
summary_file = HTML_DIR / "exploration_summary.json"
summary_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n{'=' * 70}")
print(f"Exploration complete. Summary: {summary_file}")
print(f"\nQuick recap:")
for r in results:
    n_links = len(r.get("download_links", []))
    print(f"  [{r['name']:20s}] status={r.get('status', '?'):>3} download_links={n_links}")
