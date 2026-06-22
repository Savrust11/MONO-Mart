"""Deep GoodsSearch inspection: wait for JS to build form1, dump the REAL
fields + the 展開単位CSV trigger + onclick handlers, then try a broad
search and capture the CSV request. Saves DOM + screenshots for analysis.
"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://to.zozo.jp/to/"
BASE = "https://to.zozo.jp/to/"
OUT = Path(__file__).parent / "html"


def login(page):
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def main():
    rep = {}
    hits = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ja-JP", viewport={"width": 1600, "height": 1100},
            accept_downloads=True,
            http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                              "password": os.environ["ZOZO_BASIC_PASSWORD"]})
        pg = ctx.new_page()

        def on_resp(r):
            try:
                ct = (r.headers.get("content-type") or "").lower()
                cd = (r.headers.get("content-disposition") or "").lower()
                if ("csv" in ct or "excel" in ct or "attachment" in cd
                        or "octet-stream" in ct or r.url.lower().endswith(".csv")):
                    hits.append({"url": r.url, "status": r.status,
                                 "method": r.request.method,
                                 "post": (r.request.post_data or "")[:2500],
                                 "ct": ct, "cd": cd[:70]})
            except Exception:
                pass
        pg.on("response", on_resp)

        try:
            login(pg)
            pg.goto(BASE + "GoodsSearch.asp?c=Init",
                    wait_until="networkidle", timeout=45_000)
            time.sleep(8)  # let page JS fully build form1
            (OUT / "goods_deep.html").write_text(pg.content(), encoding="utf-8")
            pg.screenshot(path=str(OUT / "goods_deep_01.png"), full_page=True)

            rep["form1"] = pg.evaluate(r"""()=>{
              const f=document.forms['form1']||
                [...document.forms].find(x=>/GoodsSearch/i.test(x.getAttribute('action')||''));
              if(!f) return null;
              return {action:f.getAttribute('action'),method:(f.getAttribute('method')||'GET').toUpperCase(),
                fields:[...f.querySelectorAll('input,select,textarea,button')].map(i=>({
                  tag:i.tagName,n:i.name||null,t:i.type||null,
                  v:(i.value||'').slice(0,30),
                  checked:i.checked||false,
                  tx:(i.innerText||'').trim().slice(0,20),
                  opts:i.tagName==='SELECT'?[...i.options].slice(0,5).map(o=>o.value):null}))};
            }""")
            rep["csv_controls"] = pg.evaluate(r"""()=>{
              const norm=s=>(s==null?'':String(s)).replace(/\s+/g,' ').trim();
              return [...document.querySelectorAll('a,button,input,span,div')].map(e=>({
                tag:e.tagName,t:norm(e.innerText||e.value).slice(0,30),
                h:e.getAttribute&&e.getAttribute('href')||'',
                oc:(e.getAttribute&&e.getAttribute('onclick')||'').slice(0,150),
                vis:!!e.offsetParent}))
                .filter(x=>/csv|ＣＳＶ|展開|ダウンロ|出力|一括委託/i.test(x.t+x.h+x.oc));
            }""")

            # broad search: click the goods page's own 検索 submit (not header)
            for sel in ("form[name=form1] input[type=submit]",
                        "form[name=form1] button[type=submit]",
                        "input[type=submit][value*='検索']",
                        "button:has-text('検索')"):
                try:
                    loc = pg.locator(sel)
                    if loc.count() > 0:
                        loc.last.click(force=True, no_wait_after=True, timeout=6000)
                        time.sleep(6)
                        break
                except Exception:
                    continue
            pg.screenshot(path=str(OUT / "goods_deep_02_searched.png"), full_page=True)
            rep["after_search_url"] = pg.url
            rep["csv_controls_after"] = pg.evaluate(r"""()=>{
              const norm=s=>(s==null?'':String(s)).replace(/\s+/g,' ').trim();
              return [...document.querySelectorAll('a,button,input')].map(e=>({
                tag:e.tagName,t:norm(e.innerText||e.value).slice(0,30),
                h:e.getAttribute&&e.getAttribute('href')||'',
                oc:(e.getAttribute&&e.getAttribute('onclick')||'').slice(0,150),
                vis:!!e.offsetParent}))
                .filter(x=>/csv|ＣＳＶ|展開|ダウンロ|出力/i.test(x.t+x.h+x.oc));
            }""")

            # click any 展開単位/CSV trigger, capture
            for t in ("展開単位CSV", "展開単位", "ＣＳＶダウンロード", "CSVダウンロード",
                      "CSV出力", "ＣＳＶ", "CSV", "ダウンロード"):
                done = False
                for sel in (f"a:has-text('{t}')", f"button:has-text('{t}')",
                            f"input[value*='{t}']"):
                    try:
                        loc = pg.locator(sel)
                        if loc.count() == 0:
                            continue
                        n0 = len(hits)
                        loc.first.click(force=True, no_wait_after=True, timeout=5000)
                        time.sleep(6)
                        if len(hits) > n0:
                            hits[-1]["fired_by"] = {"text": t, "sel": sel}
                            done = True
                            break
                    except Exception:
                        continue
                if done:
                    break
            rep["hits"] = hits
        except Exception as e:
            rep["fatal"] = str(e)[:200]
        finally:
            ctx.close(); b.close()
    (OUT / "goods_deep.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    f1 = rep.get("form1")
    print("form1:", "FOUND" if f1 else "NONE")
    if f1:
        print("  action=", f1["action"], "method=", f1["method"])
        named = [(x["n"], x["t"], x["v"], x["tx"]) for x in f1["fields"] if x["n"] or x["tx"]]
        for x in named[:25]:
            print("   ", x)
    print("csv_controls(init):", rep.get("csv_controls"))
    print("after_search_url:", rep.get("after_search_url"))
    print("csv_controls(after):", rep.get("csv_controls_after"))
    print("CSV HITS:", len(hits))
    for h in hits:
        print("  ", h["method"], h["url"], "| post:", h["post"][:400])
    print("fatal:", rep.get("fatal"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
