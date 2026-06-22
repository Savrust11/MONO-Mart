"""Use the saved Tableau session + vizportal API to list workbooks & views
and find the exact view content-URLs for 予約管理 / 発注管理."""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

SESS = Path(__file__).parent / "sessions"
STATE = SESS / "tableau_state.json"
HOST = "https://prod-apnortheast-a.online.tableau.com"


def main():
    rep = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=str(STATE), locale="ja-JP")
        pg = ctx.new_page()
        # touch the site so vizportal cookies/XSRF are active
        pg.goto(HOST + "/#/site/sitaterunext/home",
                wait_until="domcontentloaded", timeout=60_000)
        time.sleep(6)
        # XSRF token from cookies
        xsrf = ""
        for c in ctx.cookies():
            if c["name"] == "XSRF-TOKEN":
                xsrf = c["value"]
        rep["xsrf_present"] = bool(xsrf)
        hdr = {"Content-Type": "application/json;charset=UTF-8",
               "X-XSRF-TOKEN": xsrf, "Accept": "application/json"}

        def vp(method, payload):
            r = ctx.request.post(
                f"{HOST}/vizportal/api/web/v1/{method}",
                data=json.dumps(payload), headers=hdr, timeout=40_000)
            try:
                return r.status, r.json()
            except Exception:
                return r.status, r.text()[:300]

        # 1) list workbooks
        st, wb = vp("getWorkbooks", {"page": {"startIndex": 0, "maxItems": 200},
                                     "order": [{"field": "name", "ascending": True}]})
        rep["getWorkbooks_status"] = st
        wbs = []
        try:
            for w in wb.get("result", {}).get("workbooks", []):
                wbs.append({"id": w.get("id"), "name": w.get("name"),
                            "contentUrl": w.get("contentUrl")})
        except Exception as e:
            rep["wb_parse_err"] = str(e)[:120]
        rep["workbooks"] = wbs

        # 2) for each interesting workbook, get its views
        rep["views"] = {}
        for w in wbs:
            nm = (w["name"] or "")
            if not any(k in nm for k in ("予約", "発注", "MONO-MART_BI", "納品", "MMS")):
                continue
            st2, vr = vp("getViewsForWorkbook", {"id": w["id"]})
            vlist = []
            try:
                for v in vr.get("result", {}).get("views", []):
                    vlist.append({"id": v.get("id"), "name": v.get("name"),
                                  "contentUrl": v.get("contentUrl"),
                                  "viewUrlName": v.get("viewUrlName")})
            except Exception:
                vlist = [{"raw": str(vr)[:200]}]
            rep["views"][f"{nm} [{w['id']}]"] = {"status": st2, "views": vlist,
                                                 "wb_contentUrl": w["contentUrl"]}
        ctx.close(); b.close()
    (SESS / "vizportal_report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print("xsrf:", rep.get("xsrf_present"), "getWorkbooks:", rep.get("getWorkbooks_status"))
    print("workbooks:")
    for w in rep.get("workbooks", []):
        print("  ", w["id"], repr(w["name"]), "contentUrl=", w["contentUrl"])
    for k, v in rep.get("views", {}).items():
        print("VIEWS for", k, "(status", v["status"], "wb_contentUrl=", v["wb_contentUrl"], ")")
        for vw in v["views"]:
            print("   ", vw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
