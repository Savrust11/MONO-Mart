"""
Deep-probe the ZOZO BO CSV *form* pages.

For each candidate CSV endpoint:
  - GET the page with the authenticated session
  - dump the full form structure (every input/select with name, type,
    value, and select options)
  - install a CSV network listener
  - submit the form (and click any CSV/ダウンロード button) with the
    target date range filled in
  - record any response that is actually CSV (url/method/postdata)

Saves: html/csvpage_<key>.json  +  html/csvpage_<key>.html
"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
BASE = "https://to.zozo.jp/to/"
OUT = Path(__file__).parent / "html"
OUT.mkdir(exist_ok=True)

TARGET = os.getenv("TARGET_DATE") or (date.today() - timedelta(days=1)).isoformat()
y, m, d = TARGET.split("-")

# key -> page url
PAGES = {
    "order_csv":        "order_csv.asp?c=Order_CSV",
    "send_csv":         "order_csv.asp?c=Send_CSV",
    "btob_order_csv":   "btob_order_csv.asp?c=BtoB_Order_CSV",
    "sales_download":   "Sales_download.asp",
    "monthend_inv":     "monthEndInventory_Download.asp",
    "manual_dl":        "ManualDownLoad.asp",
    "reserve":          "Reserve.asp?c=ReserveList",
    "goods_search":     "GoodsSearch.asp?c=Init",
    "advertisement":    "Advertisement.asp",
    "zaiko_ok":         "zaiko_csv2.asp?c=Zaiko",   # known-good control
}


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def dump_forms(page):
    return page.evaluate(r"""() => {
      return [...document.querySelectorAll('form')].map(f => ({
        action: f.getAttribute('action'), method: (f.getAttribute('method')||'GET').toUpperCase(),
        name: f.name, id: f.id,
        fields: [...f.querySelectorAll('input,select,textarea,button')].map(i => ({
          tag: i.tagName, type: i.type||null, name: i.name||null,
          value: (i.type==='password'?'***':(i.value||'')).slice(0,40),
          text: (i.innerText||'').trim().slice(0,30),
          options: i.tagName==='SELECT'
            ? [...i.options].slice(0,8).map(o=>({v:o.value,t:o.text.slice(0,20)})) : null
        }))
      }));
    }""")


def probe(ctx, key, url):
    page = ctx.new_page()
    hits = []

    def on_resp(r):
        try:
            ct = (r.headers.get("content-type") or "").lower()
            cd = (r.headers.get("content-disposition") or "").lower()
            if ("csv" in ct or "attachment" in cd or "octet-stream" in ct
                    or r.url.lower().endswith(".csv")):
                hits.append({"url": r.url, "status": r.status,
                             "method": r.request.method,
                             "post_data": (r.request.post_data or "")[:1500],
                             "ct": ct, "cd": cd})
        except Exception:
            pass

    page.on("response", on_resp)
    rec = {"key": key, "url": url, "target": TARGET}
    try:
        login(page)
        page.goto(BASE + url, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(2)
        rec["final_url"] = page.url
        rec["title"] = page.title()
        html = page.content()
        (OUT / f"csvpage_{key}.html").write_text(html, encoding="utf-8")
        rec["html_len"] = len(html)
        rec["is_error"] = ("Message" in page.url or "Error" in page.url
                           or "404" in page.title())
        rec["forms"] = dump_forms(page)

        # Best-effort: fill any date-ish text inputs then submit / click CSV.
        if not rec["is_error"]:
            for pat in (TARGET, f"{y}/{m}/{d}", f"{y}{m}{d}"):
                try:
                    dints = page.locator("input[type=date]")
                    for i in range(min(dints.count(), 4)):
                        dints.nth(i).fill(TARGET, timeout=1500)
                except Exception:
                    pass
                break
            # try clicking submit / CSV / ダウンロード buttons & inputs
            for sel in ("input[type=submit]", "button[type=submit]",
                        "input[value*='CSV']", "input[value*='ダウンロード']",
                        "button:has-text('CSV')", "button:has-text('ダウンロード')",
                        "a:has-text('CSV')", "a:has-text('ダウンロード')",
                        "input[value*='検索']", "button:has-text('検索')"):
                try:
                    loc = page.locator(sel)
                    if loc.count() == 0:
                        continue
                    n0 = len(hits)
                    loc.first.click(force=True, no_wait_after=True, timeout=5000)
                    time.sleep(3.5)
                    if len(hits) > n0:
                        hits[-1]["fired_by"] = sel
                        break
                except Exception:
                    continue
        rec["csv_hits"] = hits
    except Exception as exc:
        rec["fatal"] = str(exc)[:200]
    finally:
        page.close()
    return rec


def main():
    for v in ("ZOZO_BASIC_USER","ZOZO_BASIC_PASSWORD","ZOZO_LOGIN_ID","ZOZO_LOGIN_PASSWORD"):
        if not os.getenv(v):
            print("missing", v); return 2
    summ = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ja-JP", viewport={"width":1440,"height":900},
            accept_downloads=True,
            http_credentials={"username":os.environ["ZOZO_BASIC_USER"],
                              "password":os.environ["ZOZO_BASIC_PASSWORD"]})
        for key, url in PAGES.items():
            r = probe(ctx, key, url)
            (OUT / f"csvpage_{key}.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
            summ.append({"key":key,"url":url,"final":r.get("final_url","")[-50:],
                         "err":r.get("is_error"),"nforms":len(r.get("forms",[])),
                         "hits":len(r.get("csv_hits",[])),
                         "hit_urls":[h["url"][-60:] for h in r.get("csv_hits",[])][:3],
                         "fatal":r.get("fatal")})
            print(json.dumps(summ[-1], ensure_ascii=False))
        ctx.close(); b.close()
    (OUT / "csvpages_summary.json").write_text(
        json.dumps(summ, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
