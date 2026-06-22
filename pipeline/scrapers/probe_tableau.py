"""Explore Tableau Cloud with the saved session: list workbooks/views and
find the 発注明細 / 予約管理 (入荷残) content + its data-CSV URL.

Tableau view data exports via the `.csv` suffix on the view path
(summary data) when authenticated by session cookies.
"""
import json, re, time
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright

SESS = Path(__file__).parent / "sessions"
HOST = "https://prod-apnortheast-a.online.tableau.com"
SITE = "sitaterunext"


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=str(SESS / "tableau_state.json"),
                             locale="ja-JP", viewport={"width": 1440, "height": 900},
                             accept_downloads=True)
        pg = ctx.new_page()
        # Explore / all workbooks
        pg.goto(f"{HOST}/#/site/{SITE}/workbooks", wait_until="domcontentloaded",
                timeout=45_000)
        time.sleep(12)  # heavy SPA — let content XHRs settle
        print("url:", pg.url)
        if "login" in pg.url.lower() or "idp" in pg.url.lower():
            print("FATAL: session invalid"); return 3

        # XSRF token from cookie → required header for vizportal API
        xsrf = ""
        for c in ctx.cookies():
            if c["name"] in ("XSRF-TOKEN", "workgroup_session_id"):
                if c["name"] == "XSRF-TOKEN":
                    xsrf = c["value"]
        hdr = {"content-type": "application/json;charset=UTF-8",
               "accept": "application/json", "X-XSRF-TOKEN": xsrf}

        wbs = []
        for ep, payload, key in [
            ("getWorkbooks", {"order": [{"field": "name", "ascending": True}],
                              "page": {"startIndex": 0, "maxItems": 800}}, "workbooks"),
            ("getViews", {"order": [{"field": "name", "ascending": True}],
                          "page": {"startIndex": 0, "maxItems": 800}}, "views"),
        ]:
            try:
                r = ctx.request.post(f"{HOST}/vizportal/api/web/v1/{ep}",
                    data=json.dumps({"method": ep, "params": payload}),
                    headers=hdr, timeout=40_000)
                if r.status == 200:
                    res = r.json().get("result", {})
                    for w in res.get(key, []):
                        wbs.append({"name": w.get("name"), "id": w.get("id"),
                                    "url": w.get("contentUrl") or w.get("urlName"),
                                    "wb": w.get("workbook", {}).get("name") if key == "views" else None})
                    print(f"{ep}: {len(res.get(key, []))} {key}")
                else:
                    print(f"{ep}: HTTP {r.status} {r.text()[:120]}")
            except Exception as e:
                print(f"{ep} failed: {str(e)[:120]}")

        # DOM fallback: scrape rendered content cards
        if not wbs:
            try:
                tiles = pg.evaluate(r"""()=>[...document.querySelectorAll(
                  'a[href*="/workbooks/"],a[href*="/views/"],[data-tb-test-id],.tb-card, [role="gridcell"]')]
                  .map(a=>({t:(a.innerText||'').trim().slice(0,50),
                            h:a.getAttribute&&a.getAttribute('href')||''}))
                  .filter(x=>x.t)""")
                wbs = [{"name": t["t"], "url": t["h"]} for t in tiles[:200]]
            except Exception:
                pass

        print(f"--- {len(wbs)} workbooks ---")
        for w in wbs:
            print("  ", w.get("name"), "| url=", w.get("url"), "| id=", w.get("id"))

        # Find 発注 / 予約 / 入荷 related workbooks and list their views
        targets = [w for w in wbs if w.get("name") and
                   re.search(r"発注|予約|入荷|納品|order|reserve|arriv", w["name"], re.I)]
        print(f"--- {len(targets)} candidate workbooks (発注/予約/入荷) ---")
        report = {"site": SITE, "workbooks": wbs, "targets": []}
        for w in targets:
            entry = {"name": w["name"], "url": w.get("url"), "id": w.get("id"), "views": []}
            try:
                r = ctx.request.post(
                    f"{HOST}/vizportal/api/web/v1/getView",
                    data=json.dumps({"method": "getViewsForWorkbook",
                                     "params": {"workbookId": w.get("id")}}),
                    headers={"content-type": "application/json;charset=UTF-8"},
                    timeout=30_000)
                if r.status == 200:
                    for v in r.json().get("result", {}).get("views", []):
                        entry["views"].append({"name": v.get("name"),
                                               "url": v.get("contentUrl")})
            except Exception as e:
                entry["views_err"] = str(e)[:100]
            print("  WB:", w["name"], "views:", entry["views"])
            report["targets"].append(entry)

        (SESS / "tableau_probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("saved tableau_probe.json")
        ctx.close(); b.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
