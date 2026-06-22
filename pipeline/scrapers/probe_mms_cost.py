"""Use the saved MMS session to locate the 原価 (ショップ別評価一覧) CSV download.

Captures any CSV/Excel network response so we can build an exact fetch recipe.
"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

SESS = Path(__file__).parent / "sessions"
STATE = SESS / "mms_state.json"
BASE = "https://mms.a-rg.work/"


def main():
    if not STATE.exists():
        print("FATAL: mms_state.json missing"); return 2
    hits = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=str(STATE), locale="ja-JP",
                            viewport={"width": 1440, "height": 900},
                            accept_downloads=True)
        page = ctx.new_page()

        def on_resp(r):
            try:
                ct = (r.headers.get("content-type") or "").lower()
                cd = (r.headers.get("content-disposition") or "").lower()
                if ("csv" in ct or "excel" in ct or "attachment" in cd
                        or "octet-stream" in ct or "spreadsheet" in ct
                        or r.url.lower().endswith(".csv")):
                    hits.append({"url": r.url, "status": r.status,
                                 "method": r.request.method,
                                 "post": (r.request.post_data or "")[:1200],
                                 "ct": ct, "cd": cd[:60]})
            except Exception:
                pass
        page.on("response", on_resp)

        page.goto(BASE + "index.php", wait_until="domcontentloaded", timeout=40_000)
        time.sleep(2)
        # Confirm session still valid (not bounced to login)
        if "login" in page.url.lower():
            print("FATAL: session expired (redirected to login)"); return 3
        print("MMS index OK:", page.url)

        # Dump all links / nav so we can find 評価額一覧 / 在庫管理
        links = page.evaluate(r"""() => [...document.querySelectorAll('a')].map(a=>({
            t:(a.innerText||'').trim().slice(0,30), h:a.getAttribute('href')||'',
            oc:(a.getAttribute('onclick')||'').slice(0,80)}))
            .filter(x=>x.t||x.h)""")
        relevant = [l for l in links if any(k in (l["t"]+l["h"]+l["oc"])
                    for k in ("評価", "在庫", "原価", "csv", "CSV", "ダウンロ",
                              "出力", "hyouka", "zaiko", "eval", "cost", "list"))]
        print("--- candidate nav links ---")
        for l in relevant[:25]:
            print(f"  '{l['t']}' h={l['h'][:55]} oc={l['oc'][:50]}")

        # Try the documented path: 在庫管理 > ショップ別評価一覧
        for label in ("在庫管理", "ショップ別評価一覧", "評価額一覧", "評価一覧"):
            try:
                lk = page.get_by_role("link", name=label)
                if lk.count() > 0:
                    lk.first.click(timeout=6000); time.sleep(2.5)
                    print(f"clicked '{label}' -> {page.url}")
            except Exception:
                pass

        # Try common direct URLs
        for u in ("hyouka_list.php", "zaiko_hyouka.php", "evaluation_list.php",
                  "shop_evaluation.php", "stock_evaluation.php"):
            try:
                page.goto(BASE + u, wait_until="domcontentloaded", timeout=15000)
                time.sleep(1.5)
                if "404" not in page.title() and "Not Found" not in page.content()[:500]:
                    print(f"reachable: {u} -> {page.url} title={page.title()[:40]}")
            except Exception:
                pass

        # try clicking CSV/ダウンロード/出力 triggers on whatever page we're on
        for t in ("CSVダウンロード", "ＣＳＶ", "CSV出力", "CSV", "ダウンロード", "出力", "エクスポート"):
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
                        print("CSV TRIGGERED by", sel)
                        break
                except Exception:
                    continue
            if hits:
                break

        rep = {"index_url": page.url, "candidate_links": relevant[:30], "hits": hits}
        (SESS / "mms_probe.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print("HITS:", json.dumps(hits, ensure_ascii=False)[:600])
        ctx.close(); b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
