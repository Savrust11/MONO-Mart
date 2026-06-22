"""
Tableau Cloud fetcher — reuses the saved session (sessions/tableau_state.json)
to download the 予約管理 and 発注管理 views as Crosstab CSV, then uploads
to GCS for the existing pipeline (tableau_extractor.py / csv_tableau_* ingest).

Flow (per the client-confirmed UI):
  workbook MONO-MART_BI_0413 → open view → toolbar Download button →
  flyout "Crosstab" → dialog: pick sheet + CSV → Download → capture file.

Heavily instrumented: screenshots at every step under sessions/tbf_*.png
and a JSON log, so the flow can be refined without guessing.

Env: GCS_RAW_BUCKET (default project bucket), TARGET_DATE (default yest JST).
"""
from __future__ import annotations
import os, sys, time, json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWT

SESS = Path(__file__).parent / "sessions"
STATE = SESS / "tableau_state.json"
HOST = "https://prod-apnortheast-a.online.tableau.com"
SITE = "sitaterunext"
WORKBOOK_ID = "4617734"   # MONO-MART_BI_0413
JST = timezone(timedelta(hours=9))

# (internal name, the view title text shown in the workbook, gcs subfolder)
TARGETS = [
    ("reserve_mgmt", "予約管理", "tableau/yoyaku"),
    ("order_mgmt",   "発注管理", "tableau/hacchu"),
]


def log(rec, m):
    line = f"{datetime.now().isoformat()} {m}"
    print(line)
    rec.setdefault("log", []).append(line)


def find_download_csv(page, rec, tag):
    """Click toolbar Download → Crosstab → CSV → Download; return Path or None."""
    def shot(s):
        try: page.screenshot(path=str(SESS / f"tbf_{tag}_{s}.png"))
        except Exception: pass

    # 1) toolbar Download button (Tableau Cloud chrome, not canvas)
    dl_sel = ("[data-tb-test-id='download-flyout-trigger-Button'], "
              "[data-tb-test-id*='download'], button[aria-label*='ダウンロード'], "
              "button[aria-label*='Download'], [aria-label='ダウンロード'], "
              "[aria-label='Download']")
    clicked = False
    for _ in range(3):
        try:
            loc = page.locator(dl_sel)
            if loc.count() > 0:
                loc.first.click(timeout=8_000)
                clicked = True
                break
        except Exception:
            pass
        time.sleep(3)
    shot("01_download_clicked")
    if not clicked:
        log(rec, f"[{tag}] download toolbar button not found")
        return None
    time.sleep(2)

    # 2) flyout → "Crosstab" / "クロス集計"
    ct_sel = ("[data-tb-test-id='download-flyout-Crosstab'], "
              "[data-tb-test-id*='Crosstab'], text=Crosstab, text=クロス集計, "
              "[role='menuitem']:has-text('Crosstab'), "
              "[role='menuitem']:has-text('クロス集計')")
    try:
        page.locator(ct_sel).first.click(timeout=8_000)
    except Exception as e:
        log(rec, f"[{tag}] Crosstab item not found: {str(e)[:100]}")
        return None
    time.sleep(3)
    shot("02_crosstab_dialog")

    # 3) dialog: select a sheet thumbnail if a list is shown, choose CSV radio
    try:
        # pick first worksheet thumbnail if the chooser is present
        thumb = page.locator("[data-tb-test-id*='sheet'], "
                             ".tabExportCrosstabDialog [role='option'], "
                             ".f1ip3pll, [class*='thumbnail']")
        if thumb.count() > 0:
            thumb.first.click(timeout=4_000)
    except Exception:
        pass
    # CSV format radio/label
    for csv_sel in ("input[type='radio'][value='csv']",
                    "label:has-text('CSV')", "text=CSV",
                    "[data-tb-test-id*='csv']", "[aria-label*='CSV']"):
        try:
            l = page.locator(csv_sel)
            if l.count() > 0:
                l.first.click(timeout=3_000)
                break
        except Exception:
            continue
    shot("03_csv_selected")

    # 4) Download button in dialog → capture file
    dlbtn = ("[data-tb-test-id='export-crosstab-export-Button'], "
             "[data-tb-test-id*='export'][data-tb-test-id*='Button'], "
             "button:has-text('ダウンロード'), button:has-text('Download')")
    try:
        with page.expect_download(timeout=120_000) as di:
            page.locator(dlbtn).first.click(timeout=10_000)
        d = di.value
        out = SESS / (d.suggested_filename or f"{tag}.csv")
        d.save_as(str(out))
        shot("04_done")
        log(rec, f"[{tag}] downloaded {out.name} ({out.stat().st_size} bytes)")
        return out
    except Exception as e:
        log(rec, f"[{tag}] download capture failed: {str(e)[:140]}")
        shot("04_fail")
        return None


def main():
    if not STATE.exists():
        print("FATAL: tableau_state.json missing — run interactive_login --target tableau")
        return 2
    target_date = os.getenv("TARGET_DATE") or (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")
    bucket = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
    rec = {"target_date": target_date, "results": []}
    ok_any = False

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=str(STATE), locale="ja-JP",
                            viewport={"width": 1680, "height": 1050},
                            accept_downloads=True)
        pg = ctx.new_page()
        try:
            pg.goto(f"{HOST}/#/site/{SITE}/workbooks/{WORKBOOK_ID}/views",
                    wait_until="domcontentloaded", timeout=60_000)
            time.sleep(12)
            pg.screenshot(path=str(SESS / "tbf_workbook.png"), full_page=True)
            # harvest the view links in this workbook
            views = pg.evaluate(r"""() => {
              const norm=s=>(s==null?'':String(s)).replace(/\s+/g,' ').trim();
              return [...document.querySelectorAll('a')].map(a=>({
                t:norm(a.innerText||a.getAttribute('aria-label')).slice(0,40),
                h:a.getAttribute('href')||''}))
                .filter(x=>x.h.includes('/views/'));
            }""")
            rec["views_found"] = views
            log(rec, f"views in workbook: {[v['t'] for v in views]}")

            for key, title, sub in TARGETS:
                vlink = None
                for v in views:
                    if title in v["t"]:
                        vlink = v["h"]; break
                if not vlink:
                    log(rec, f"[{key}] view '{title}' not found in workbook")
                    rec["results"].append({"key": key, "status": "view_not_found"})
                    continue
                url = vlink if vlink.startswith("http") else HOST + vlink
                log(rec, f"[{key}] opening {url}")
                pg.goto(url, wait_until="domcontentloaded", timeout=60_000)
                time.sleep(18)  # viz fully render
                pg.screenshot(path=str(SESS / f"tbf_{key}_view.png"))
                f = find_download_csv(pg, rec, key)
                if f and f.stat().st_size > 100:
                    # upload to GCS
                    try:
                        from google.cloud import storage
                        gp = f"uploads/{sub}/{target_date}/{f.name}"
                        storage.Client().bucket(bucket).blob(gp).upload_from_filename(str(f))
                        log(rec, f"[{key}] → gs://{bucket}/{gp}")
                        rec["results"].append({"key": key, "status": "ok",
                                               "gcs": f"gs://{bucket}/{gp}",
                                               "bytes": f.stat().st_size})
                        ok_any = True
                    except Exception as e:
                        log(rec, f"[{key}] GCS upload failed: {str(e)[:120]}")
                        rec["results"].append({"key": key, "status": "gcs_fail"})
                else:
                    rec["results"].append({"key": key, "status": "download_failed"})
        except Exception as e:
            rec["fatal"] = str(e)[:200]
            log(rec, f"FATAL {e}")
        finally:
            ctx.close(); b.close()
    (SESS / "tbf_report.json").write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESULTS:", json.dumps(rec["results"], ensure_ascii=False))
    return 0 if ok_any else 1


if __name__ == "__main__":
    sys.exit(main())
