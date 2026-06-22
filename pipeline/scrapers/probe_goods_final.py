"""Final GoodsSearch attempt: click the SPECIFIC page search button
(button[name=search][value=SEARCH]), reach results, capture the
展開単位CSV request (full network log). Same-origin ASP — replayable."""
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
    rep = {"net": []}
    csvhits = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(locale="ja-JP", viewport={"width": 1600, "height": 1100},
            accept_downloads=True,
            http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                              "password": os.environ["ZOZO_BASIC_PASSWORD"]})
        pg = ctx.new_page()

        def on_req(r):
            try:
                if r.method == "POST" or "csv" in r.url.lower() or "Goods" in r.url:
                    rep["net"].append({"m": r.method, "u": r.url[:120],
                                       "pd": (r.post_data or "")[:400]})
            except Exception:
                pass

        def on_resp(r):
            try:
                ct = (r.headers.get("content-type") or "").lower()
                cd = (r.headers.get("content-disposition") or "").lower()
                if ("csv" in ct or "excel" in ct or "attachment" in cd
                        or "octet-stream" in ct or r.url.lower().endswith(".csv")):
                    csvhits.append({"url": r.url, "status": r.status,
                                    "method": r.request.method,
                                    "post": (r.request.post_data or "")[:1500],
                                    "ct": ct, "cd": cd[:70]})
            except Exception:
                pass
        pg.on("request", on_req)
        pg.on("response", on_resp)

        try:
            login(pg)
            pg.goto(BASE + "GoodsSearch.asp?c=Init",
                    wait_until="networkidle", timeout=45_000)
            time.sleep(6)
            # the actual page search button: btn-primary, type=submit, name=search, value=SEARCH
            btn = pg.locator("button[name='search'][value='SEARCH'], "
                             "button.btn-primary[type='submit']:has-text('検索')")
            rep["search_btn_count"] = btn.count()
            if btn.count() > 0:
                btn.first.click(timeout=10_000)
                time.sleep(8)  # results render
            rep["after_search_url"] = pg.url
            pg.screenshot(path=str(OUT / "goods_final_results.png"), full_page=True)
            (OUT / "goods_final_results.html").write_text(pg.content(), encoding="utf-8")

            # On results: find the 展開単位CSV / CSV download trigger
            rep["result_csv_ctl"] = pg.evaluate(r"""()=>{
              const norm=s=>(s==null?'':String(s)).replace(/\s+/g,' ').trim();
              return [...document.querySelectorAll('a,button,input')].map(e=>({
                tag:e.tagName,t:norm(e.innerText||e.value).slice(0,30),
                h:e.getAttribute&&e.getAttribute('href')||'',
                nm:e.getAttribute&&e.getAttribute('name')||'',
                oc:(e.getAttribute&&e.getAttribute('onclick')||'').slice(0,160),
                vis:!!e.offsetParent}))
                .filter(x=>/csv|ＣＳＶ|展開|ダウンロ|出力/i.test(x.t+x.h+x.oc+x.nm)
                           && !/dropdown-link/.test(x.oc));
            }""")
            # try clicking each candidate, capture CSV
            for t in ("展開単位CSV", "展開単位", "ＣＳＶダウンロード", "CSVダウンロード",
                      "CSV出力", "ＣＳＶ", "CSV", "ダウンロード"):
                done = False
                for sel in (f"a:has-text('{t}')", f"button:has-text('{t}')",
                            f"input[value*='{t}']",
                            f"button[name*='csv' i]", f"a[href*='Csv' i]"):
                    try:
                        loc = pg.locator(sel)
                        if loc.count() == 0:
                            continue
                        n0 = len(csvhits)
                        loc.first.click(force=True, no_wait_after=True, timeout=5000)
                        time.sleep(6)
                        if len(csvhits) > n0:
                            csvhits[-1]["fired_by"] = {"text": t, "sel": sel}
                            done = True
                            break
                    except Exception:
                        continue
                if done:
                    break
            rep["csvhits"] = csvhits
        except Exception as e:
            rep["fatal"] = str(e)[:200]
        finally:
            ctx.close(); b.close()
    (OUT / "goods_final.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("search_btn_count:", rep.get("search_btn_count"))
    print("after_search_url:", rep.get("after_search_url"))
    print("result_csv_ctl:", json.dumps(rep.get("result_csv_ctl", []), ensure_ascii=False)[:600])
    print("CSV HITS:", len(csvhits))
    for h in csvhits:
        print("  ", h["method"], h["url"], "| post:", h["post"][:500])
    print("--- POST/Goods net (last 12) ---")
    for n in rep["net"][-12:]:
        print("  ", n["m"], n["u"], "| pd:", n["pd"][:200])
    print("fatal:", rep.get("fatal"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
