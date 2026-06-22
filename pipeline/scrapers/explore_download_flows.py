"""
Reverse-engineer the real CSV-download flow for each ZOZO BO source.

For every source it:
  1. logs in (2-stage)
  2. navigates to the data page (direct, then via menu if rejected)
  3. records EVERY form (action/method/all inputs incl. hidden)
  4. records every element whose text/value/href looks like a CSV trigger
  5. installs a network listener that captures any response that is a CSV
     (content-disposition: attachment / content-type csv / .csv URL)
  6. clicks each candidate trigger and records which network request
     produced the CSV (URL, method, post-data) — that is the recipe.

Output: pipeline/scrapers/html/flow_<name>.json  (one per source)
        pipeline/scrapers/html/flows_summary.json

Run with Python 3.13:
  $env:ZOZO_BASIC_USER=...  (etc, 4 creds)
  python pipeline/scrapers/explore_download_flows.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

LOGIN_URL = "https://to.zozo.jp/to/"
BASE = "https://to.zozo.jp/to/"
OUT = Path(__file__).parent / "html"
OUT.mkdir(exist_ok=True)

# (name, primary page URL, menu link text to fall back to)
SOURCES = [
    ("orders",         "Order.asp?c=Init",          "受注"),
    ("shipped",        "Order.asp?c=Init",          "発送"),
    ("reservations",   "Reserve.asp?c=ReserveList", "予約"),
    ("zozoad",         "Advertisement.asp",         "ZOZOAD"),
    ("product_master", "GoodsSearch.asp?c=Init",    "登録商品"),
    ("performance",    "LookerDashboards.asp",      "商品別実績"),
    ("sale_settings",  "SaleSetting.asp",           "セール設定"),
]


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def snapshot_forms(page):
    return page.evaluate("""() => {
      return [...document.querySelectorAll('form')].map(f => ({
        action: f.getAttribute('action'),
        method: (f.getAttribute('method')||'GET').toUpperCase(),
        id: f.id, name: f.name,
        inputs: [...f.querySelectorAll('input,select,textarea')].map(i => ({
          tag: i.tagName, type: i.type||null, name: i.name||null,
          value: (i.type==='password'?'***':(i.value||'')).slice(0,60)
        }))
      }));
    }""")


def snapshot_triggers(page):
    return page.evaluate(r"""() => {
      const pat = /csv|ＣＳＶ|ダウンロ|download|出力|エクスポート|DL/i;
      const out = [];
      for (const el of document.querySelectorAll('a,button,input')) {
        const txt = (el.innerText||el.value||'').trim().slice(0,40);
        const href = el.getAttribute('href')||'';
        const oc = el.getAttribute('onclick')||'';
        if (pat.test(txt) || pat.test(href) || pat.test(oc)) {
          out.push({tag: el.tagName, text: txt, href: href,
                    onclick: oc.slice(0,160),
                    visible: !!(el.offsetParent),
                    id: el.id||null, cls: el.className||null});
        }
      }
      return out;
    }""")


def explore_one(ctx, name, page_url, menu_text):
    page = ctx.new_page()
    rec = {"name": name, "page_url": page_url, "csv_hits": [],
           "all_requests": []}

    csv_hits = []

    def on_response(resp):
        try:
            ct = (resp.headers.get("content-type") or "").lower()
            cd = (resp.headers.get("content-disposition") or "").lower()
            url = resp.url
            is_csv = ("csv" in ct or "attachment" in cd or "octet-stream" in ct
                      or url.lower().endswith(".csv"))
            if is_csv:
                req = resp.request
                csv_hits.append({
                    "url": url, "status": resp.status,
                    "method": req.method,
                    "post_data": (req.post_data or "")[:1000],
                    "content_type": ct, "content_disposition": cd,
                })
        except Exception:
            pass

    page.on("response", on_response)

    try:
        login(page)
        # 1) direct
        page.goto(BASE + page_url, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(2)
        rec["direct_final_url"] = page.url
        rec["direct_title"] = page.title()

        rejected = ("Message" in page.url or "Error" in page.url
                    or "404" in page.title())
        if rejected and menu_text:
            # 2) via menu — go to dashboard then click the menu link
            page.goto(BASE + "main.asp?Init", wait_until="domcontentloaded",
                      timeout=30_000)
            time.sleep(1.5)
            try:
                link = page.get_by_role("link", name=menu_text).first
                if link.count() > 0:
                    link.hover()
                    time.sleep(0.8)
                    link.click(timeout=8_000)
                    time.sleep(2.5)
            except Exception as exc:
                rec["menu_nav_error"] = str(exc)[:160]
            rec["menu_final_url"] = page.url
            rec["menu_title"] = page.title()

        rec["forms"] = snapshot_forms(page)
        rec["triggers"] = snapshot_triggers(page)

        # 3) try each trigger, watch for CSV network hit
        for i, t in enumerate(rec["triggers"][:12]):
            sel = None
            if t["id"]:
                sel = f"#{t['id']}"
            elif t["text"]:
                tag = t["tag"].lower()
                sel = f"{tag}:has-text('{t['text'][:20]}')"
            if not sel:
                continue
            try:
                before = len(csv_hits)
                loc = page.locator(sel)
                if loc.count() == 0:
                    continue
                loc.first.click(force=True, no_wait_after=True, timeout=6_000)
                time.sleep(4)
                if len(csv_hits) > before:
                    csv_hits[-1]["fired_by"] = {"sel": sel, "text": t["text"]}
                # if navigated away, go back to the data page
                if "Message" in page.url or page.url == LOGIN_URL:
                    break
            except Exception:
                continue

        # 4) also probe the ManualDownLoad / download center
        try:
            page.goto(BASE + "ManualDownLoad.asp",
                      wait_until="domcontentloaded", timeout=20_000)
            time.sleep(1.5)
            rec["manual_center_triggers"] = snapshot_triggers(page)
            rec["manual_center_forms"] = snapshot_forms(page)
        except Exception:
            pass

        rec["csv_hits"] = csv_hits
    except Exception as exc:
        rec["fatal"] = str(exc)[:240]
    finally:
        page.close()
    return rec


def main():
    for v in ("ZOZO_BASIC_USER", "ZOZO_BASIC_PASSWORD",
              "ZOZO_LOGIN_ID", "ZOZO_LOGIN_PASSWORD"):
        if not os.getenv(v):
            print(f"Missing {v}")
            return 2

    summary = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="ja-JP", viewport={"width": 1440, "height": 900},
            accept_downloads=True,
            http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                              "password": os.environ["ZOZO_BASIC_PASSWORD"]},
        )
        for name, page_url, menu in SOURCES:
            print(f"=== {name} ===")
            rec = explore_one(ctx, name, page_url, menu)
            (OUT / f"flow_{name}.json").write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            summary.append({
                "name": name,
                "direct_final_url": rec.get("direct_final_url"),
                "menu_final_url": rec.get("menu_final_url"),
                "n_forms": len(rec.get("forms", [])),
                "n_triggers": len(rec.get("triggers", [])),
                "n_csv_hits": len(rec.get("csv_hits", [])),
                "csv_urls": [h["url"] for h in rec.get("csv_hits", [])][:5],
                "fatal": rec.get("fatal"),
            })
            print(json.dumps(summary[-1], ensure_ascii=False))
        ctx.close()
        browser.close()

    (OUT / "flows_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nDONE → pipeline/scrapers/html/flows_summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
