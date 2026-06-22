"""Targeted probe for reservations, product_master, sale_settings, zozoad.

For each: navigate to the page, submit its search/download form, then
capture any CSV network response (url/method/post_data) so we can build
an exact replay recipe.
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


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def cap(page):
    hits = []
    def on_resp(r):
        try:
            ct = (r.headers.get("content-type") or "").lower()
            cd = (r.headers.get("content-disposition") or "").lower()
            if ("csv" in ct or "excel" in ct or "attachment" in cd
                    or "octet-stream" in ct or r.url.lower().endswith(".csv")):
                hits.append({"url": r.url, "status": r.status,
                             "method": r.request.method,
                             "post_data": (r.request.post_data or "")[:1800],
                             "ct": ct, "cd": cd[:60]})
        except Exception:
            pass
    page.on("response", on_resp)
    return hits


def all_buttons(page):
    """Return every button/link/submit with its text & onclick for inspection."""
    return page.evaluate(r"""() => [...document.querySelectorAll(
        'a,button,input[type=submit],input[type=button]')].map(e => ({
        tag:e.tagName, t:(e.innerText||e.value||'').trim().slice(0,30),
        href:e.getAttribute('href')||'', oc:(e.getAttribute('onclick')||'').slice(0,120),
        vis:!!e.offsetParent})).filter(x=>x.t||x.href||x.oc)""")


def try_clicks(page, hits, texts):
    for t in texts:
        for sel in (f"a:has-text('{t}')", f"button:has-text('{t}')",
                    f"input[value*='{t}']"):
            try:
                loc = page.locator(sel)
                if loc.count() == 0:
                    continue
                n = len(hits)
                loc.first.click(force=True, no_wait_after=True, timeout=5000)
                time.sleep(4)
                if len(hits) > n:
                    hits[-1]["fired_by"] = sel
                    return True
            except Exception:
                continue
    return False


def probe_reservations(ctx):
    page = ctx.new_page(); hits = cap(page); login(page)
    page.goto(BASE + "Reserve.asp?c=ReserveList", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(2)
    rec = {"name": "reservations", "buttons": all_buttons(page)}
    # submit the search form (form1, c=SearchList) selecting all shops
    try:
        page.evaluate("""() => {
          const f=document.forms['form1']; if(!f) return;
          if(f.ShopID) f.ShopID.value='-1';
          f.submit();
        }""")
        time.sleep(3)
    except Exception as e:
        rec["search_err"] = str(e)[:120]
    rec["after_search_url"] = page.url
    rec["buttons_after"] = all_buttons(page)
    try_clicks(page, hits, ["CSVダウンロード", "ＣＳＶ", "CSV", "ダウンロード", "一覧出力", "出力"])
    rec["hits"] = hits
    page.close(); return rec


def probe_goods(ctx):
    page = ctx.new_page(); hits = cap(page); login(page)
    page.goto(BASE + "GoodsSearch.asp?c=Init", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(2)
    rec = {"name": "product_master", "buttons": all_buttons(page)}
    try:
        page.evaluate("""() => { const f=document.forms['form1']; if(f) f.submit(); }""")
        time.sleep(3)
    except Exception as e:
        rec["search_err"] = str(e)[:120]
    rec["after_url"] = page.url
    rec["buttons_after"] = all_buttons(page)
    try_clicks(page, hits, ["CSV", "ＣＳＶ", "ダウンロード", "登録商品", "一覧", "出力", "エクスポート"])
    rec["hits"] = hits
    page.close(); return rec


def probe_sales_dl(ctx):
    page = ctx.new_page(); hits = cap(page); login(page)
    page.goto(BASE + "Sales_download.asp", wait_until="domcontentloaded", timeout=30_000)
    time.sleep(2)
    rec = {"name": "sale_settings", "buttons": all_buttons(page)}
    # find the DownloadForm_* form and submit it directly
    info = page.evaluate(r"""() => {
      for (const f of document.forms) {
        const c=f.querySelector("input[name='c']");
        if (c && c.value && /downl/i.test(c.value)) {
          return {name:f.name, action:f.getAttribute('action'),
            fields:[...f.querySelectorAll('input,select')].map(i=>({n:i.name,v:i.value}))};
        }
      }
      return null;
    }""")
    rec["download_form"] = info
    try:
        if info:
            page.evaluate(f"""() => {{
              const f=document.forms['{info['name']}']||
                [...document.forms].find(x=>x.getAttribute('action') && /Sales_download/i.test(x.getAttribute('action')));
              if(f) f.submit();
            }}""")
            time.sleep(4)
    except Exception as e:
        rec["submit_err"] = str(e)[:120]
    try_clicks(page, hits, ["ダウンロード", "CSV", "ＣＳＶ", "DL"])
    rec["hits"] = hits
    page.close(); return rec


def probe_zozoad(ctx):
    page = ctx.new_page(); hits = cap(page); login(page)
    rec = {"name": "zozoad"}
    for url in ("Advertisement.asp", "Advertisement.asp?c=Report",
                "Advertisement.asp?c=Detail", "AdvertisementReport.asp",
                "Ad_Report.asp", "Advertisement.asp?c=Init"):
        try:
            page.goto(BASE + url, wait_until="domcontentloaded", timeout=20_000)
            time.sleep(1.5)
            if "Message" not in page.url and "404" not in page.title():
                rec.setdefault("reachable", []).append({"url": url, "final": page.url[-50:]})
        except Exception:
            continue
    page.goto(BASE + "Advertisement.asp", wait_until="domcontentloaded", timeout=20_000)
    time.sleep(1.5)
    rec["buttons"] = all_buttons(page)
    try_clicks(page, hits, ["CSV", "ＣＳＶ", "ダウンロード", "レポート", "実績", "ダウンロ", "出力"])
    rec["hits"] = hits
    page.close(); return rec


def main():
    for v in ("ZOZO_BASIC_USER","ZOZO_BASIC_PASSWORD","ZOZO_LOGIN_ID","ZOZO_LOGIN_PASSWORD"):
        if not os.getenv(v):
            print("missing", v); return 2
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ja-JP", viewport={"width":1440,"height":900},
            accept_downloads=True,
            http_credentials={"username":os.environ["ZOZO_BASIC_USER"],
                              "password":os.environ["ZOZO_BASIC_PASSWORD"]})
        for fn in (probe_reservations, probe_goods, probe_sales_dl, probe_zozoad):
            try:
                r = fn(ctx)
            except Exception as e:
                r = {"name": fn.__name__, "fatal": str(e)[:200]}
            (OUT / f"rem_{r['name']}.json").write_text(
                json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
            print(r["name"], "hits=", len(r.get("hits", [])),
                  [h["url"][-55:] for h in r.get("hits", [])][:3],
                  "fatal=", r.get("fatal"))
        ctx.close(); b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
