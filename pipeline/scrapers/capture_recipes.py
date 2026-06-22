"""Definitively capture the CSV-POST recipe for stock_analysis, product_master,
reservations, zozoad by submitting each page's real form and recording the
exact network request that returns CSV.

For each: login → goto page → dump every form (full fields) → submit the
list/search form → click each CSV/出力/ダウンロード candidate while a network
listener records any CSV response (url, method, full post_data).
"""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
BASE = "https://to.zozo.jp/to/"
OUT = Path(__file__).parent / "html"
T = os.getenv("TARGET_DATE") or (date.today() - timedelta(days=1)).isoformat()

PAGES = {
    "stock_analysis": "StockAnalysis.asp?c=init",
    "product_master": "GoodsSearch.asp?c=Init",
    "reservations":   "Reserve.asp?c=ReserveList",
    "zozoad":         "Advertisement.asp",
}


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def dump_forms(page):
    return page.evaluate(r"""() => [...document.forms].map(f => ({
      name:f.name, action:f.getAttribute('action'),
      method:(f.getAttribute('method')||'GET').toUpperCase(),
      fields:[...f.querySelectorAll('input,select,textarea,button')].map(i=>({
        tag:i.tagName, type:i.type||null, name:i.name||null,
        value:(i.type==='password'?'***':(i.value||'')).slice(0,50),
        text:(i.innerText||'').trim().slice(0,28),
        checked:i.checked||false,
        opts:i.tagName==='SELECT'?[...i.options].slice(0,6).map(o=>o.value):null
      }))
    }))""")


def capture(ctx, name, url):
    page = ctx.new_page()
    hits = []

    def on_resp(r):
        try:
            ct = (r.headers.get("content-type") or "").lower()
            cd = (r.headers.get("content-disposition") or "").lower()
            if ("csv" in ct or "excel" in ct or "attachment" in cd
                    or "octet-stream" in ct or r.url.lower().endswith(".csv")):
                hits.append({"url": r.url, "status": r.status,
                             "method": r.request.method,
                             "post_data": (r.request.post_data or "")[:2000],
                             "ct": ct, "cd": cd[:70]})
        except Exception:
            pass

    page.on("response", on_resp)
    rec = {"name": name, "url": url}
    try:
        login(page)
        page.goto(BASE + url, wait_until="domcontentloaded", timeout=40_000)
        time.sleep(2.5)
        rec["final_url"] = page.url
        rec["forms_initial"] = dump_forms(page)
        (OUT / f"cap_{name}.html").write_text(page.content(), encoding="utf-8")

        # 1) Submit the main list/search form (the non-password, non-header one)
        try:
            page.evaluate(r"""() => {
              for (const f of document.forms) {
                const c=f.querySelector("input[name='c']");
                const cv=c?c.value:'';
                if (/SearchList|init|List|Search|Zaiko|Stock/i.test(cv)
                    && !/ChangePass|HeaderSearch/i.test(cv)) {
                  const s=f.querySelector("select[name='ShopID']"); if(s) s.value='-1';
                  f.submit(); return cv;
                }
              }
            }""")
            time.sleep(3.5)
        except Exception as e:
            rec["submit_err"] = str(e)[:120]
        rec["after_submit_url"] = page.url
        rec["forms_after"] = dump_forms(page)

        # 2) Click every plausible CSV/download/出力 trigger
        texts = ["CSVダウンロード", "ＣＳＶダウンロード", "CSV出力", "CSVﾀﾞｳﾝﾛｰﾄﾞ",
                 "一覧出力", "ダウンロード", "ＣＳＶ", "CSV", "出力", "エクスポート",
                 "ダウンロ", "DL"]
        for t in texts:
            for sel in (f"a:has-text('{t}')", f"button:has-text('{t}')",
                        f"input[type=submit][value*='{t}']",
                        f"input[type=button][value*='{t}']",
                        f"span:has-text('{t}')"):
                try:
                    loc = page.locator(sel)
                    if loc.count() == 0:
                        continue
                    n = len(hits)
                    loc.first.click(force=True, no_wait_after=True, timeout=5000)
                    time.sleep(4)
                    if len(hits) > n:
                        hits[-1]["fired_by"] = {"text": t, "sel": sel}
                        rec["hits"] = hits
                        page.close()
                        return rec
                except Exception:
                    continue
        rec["hits"] = hits
    except Exception as exc:
        rec["fatal"] = str(exc)[:200]
    finally:
        page.close()
    return rec


def main():
    for v in ("ZOZO_BASIC_USER","ZOZO_BASIC_PASSWORD","ZOZO_LOGIN_ID","ZOZO_LOGIN_PASSWORD"):
        if not os.getenv(v):
            print("missing", v); return 2
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ja-JP", viewport={"width":1440,"height":1000},
            accept_downloads=True,
            http_credentials={"username":os.environ["ZOZO_BASIC_USER"],
                              "password":os.environ["ZOZO_BASIC_PASSWORD"]})
        for name, url in PAGES.items():
            r = capture(ctx, name, url)
            (OUT / f"cap_{name}.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
            h = r.get("hits", [])
            print(f"{name}: hits={len(h)} "
                  + (json.dumps(h[0], ensure_ascii=False)[:300] if h else
                     f"NO CSV (after={r.get('after_submit_url','')[-45:]} fatal={r.get('fatal')})"))
        ctx.close(); b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
