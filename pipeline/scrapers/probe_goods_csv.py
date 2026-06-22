"""Capture the 登録商品(SKU単位) 展開単位CSV recipe from ZOZO BO GoodsSearch.

Logs in (2-stage), opens GoodsSearch.asp?c=Init, submits a broad search
(no restricting filters so CSV出力 is allowed), then clicks every
CSV/展開単位/ダウンロード candidate while capturing the network request
that returns CSV (url/method/post_data) — so we can replay it.
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
        ctx = b.new_context(locale="ja-JP", viewport={"width": 1500, "height": 1000},
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
                                 "post": (r.request.post_data or "")[:2000],
                                 "ct": ct, "cd": cd[:70]})
            except Exception:
                pass
        pg.on("response", on_resp)

        try:
            login(pg)
            print("logged in", pg.url)
            pg.goto(BASE + "GoodsSearch.asp?c=Init",
                    wait_until="domcontentloaded", timeout=40_000)
            time.sleep(4)
            rep["init_url"] = pg.url
            pg.screenshot(path=str(OUT / "goods_01_init.png"), full_page=True)

            # dump all forms + csv/展開/ダウンロード controls
            rep["controls"] = pg.evaluate(r"""()=>{
              const norm=s=>(s==null?'':String(s)).replace(/\s+/g,' ').trim();
              const forms=[...document.forms].map(f=>({name:f.name,
                action:f.getAttribute('action'),method:(f.getAttribute('method')||'GET').toUpperCase(),
                fields:[...f.querySelectorAll('input,select,button')].slice(0,40).map(i=>({
                  n:i.name,t:i.type,v:(i.value||'').slice(0,24),tx:(i.innerText||'').trim().slice(0,18)}))}));
              const ctl=[...document.querySelectorAll('a,button,input')].map(e=>({
                tag:e.tagName,t:norm(e.innerText||e.value),h:e.getAttribute('href')||'',
                oc:(e.getAttribute('onclick')||'').slice(0,120),vis:!!e.offsetParent}))
                .filter(x=>/csv|ＣＳＶ|展開|ダウンロ|出力|検索/i.test(x.t+x.h+x.oc));
              return {forms,ctl};
            }""")

            # 1) submit the search (form1 / 検索 button) with no restricting filters
            for sel in ("input[type=submit][value*='検索']",
                        "button:has-text('検索')", "a:has-text('検索')",
                        "input[value*='検索']"):
                try:
                    loc = pg.locator(sel)
                    if loc.count() > 0:
                        loc.first.click(force=True, no_wait_after=True, timeout=6000)
                        time.sleep(5)
                        break
                except Exception:
                    continue
            pg.screenshot(path=str(OUT / "goods_02_searched.png"), full_page=True)
            rep["after_search_url"] = pg.url

            # 2) click every CSV / 展開単位 / ダウンロード trigger, capture CSV
            for t in ("展開単位CSV", "展開単位", "ＣＳＶダウンロード", "CSVダウンロード",
                      "CSV出力", "ＣＳＶ", "CSV", "ダウンロード", "一括委託返却用CSV",
                      "出力"):
                fired = False
                for sel in (f"a:has-text('{t}')", f"button:has-text('{t}')",
                            f"input[type=submit][value*='{t}']",
                            f"input[type=button][value*='{t}']"):
                    try:
                        loc = pg.locator(sel)
                        if loc.count() == 0:
                            continue
                        n0 = len(hits)
                        loc.first.click(force=True, no_wait_after=True, timeout=5000)
                        time.sleep(5)
                        if len(hits) > n0:
                            hits[-1]["fired_by"] = {"text": t, "sel": sel}
                            fired = True
                            break
                    except Exception:
                        continue
                if fired:
                    break
            rep["hits"] = hits
        except Exception as e:
            rep["fatal"] = str(e)[:200]
        finally:
            ctx.close(); b.close()
    (OUT / "goods_probe.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("init:", rep.get("init_url"), "after_search:", rep.get("after_search_url"))
    print("forms:")
    for f in rep.get("controls", {}).get("forms", []):
        ff = [(x["n"], x["t"], x["v"], x["tx"]) for x in f["fields"] if x["n"] or x["tx"]]
        if ff:
            print("  ", f["method"], f["action"], ff[:12])
    print("ctl:")
    for c in rep.get("controls", {}).get("ctl", [])[:14]:
        print("  ", c["tag"], repr(c["t"][:24]), "h=", c["h"][:45], "oc=", c["oc"][:60])
    print("CSV HITS:", len(hits))
    for h in hits:
        print("  ", h["method"], h["url"], "| post:", h["post"][:300])
    print("fatal:", rep.get("fatal"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
