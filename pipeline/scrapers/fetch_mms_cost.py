"""
Automated 原価 (MMS ショップ別評価額一覧) fetcher — No.10 原価.

MMS valuation_list.php does NOT support "all shops" (全て → 0 rows). The
評価額一覧 must be pulled per-shop: select shop_id → 検索 (do=1) → click the
client-side "CSVとして保存" button (a real browser download). We iterate every
shop, merge the per-shop CSVs (header kept once) and upload the combined
file to the path run_csv_ingestion expects:

    gs://{bucket}/uploads/mms/cost/{date}/評価額一覧-MMS.csv

Uses the saved MMS session (sessions/mms_state.json); re-logs in with
LOGIN_USER/LOGIN_PASS (MMS has no 2FA) if the session expired.

Run:  TARGET_DATE=2026-05-15 python fetch_mms_cost.py
"""
from __future__ import annotations
import os, sys, time
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright
from google.cloud import storage

SESS = Path(__file__).parent / "sessions"
STATE = SESS / "mms_state.json"
BASE = "https://mms.a-rg.work/"
VALUATION = BASE + "valuation_list.php"
LOGIN = BASE + "login.php"

TARGET = os.getenv("TARGET_DATE") or (date.today() - timedelta(days=1)).isoformat()
BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
GCS_PATH = f"uploads/mms/cost/{TARGET}/評価額一覧-MMS.csv"


def _login(ctx) -> None:
    u, pw = os.environ.get("LOGIN_USER"), os.environ.get("LOGIN_PASS")
    if not u or not pw:
        raise RuntimeError("session expired and LOGIN_USER/LOGIN_PASS not set")
    pg = ctx.new_page()
    pg.goto(LOGIN, wait_until="domcontentloaded", timeout=40_000)
    pg.locator("#user_id, input[name='user_id']").first.fill(u, timeout=15_000)
    pg.locator("#passwd, input[name='passwd']").first.fill(pw, timeout=15_000)
    pg.locator("button[type='submit'], input[type='submit']").first.click(timeout=10_000)
    pg.wait_for_load_state("domcontentloaded"); time.sleep(3)
    if "login" in pg.url.lower():
        raise RuntimeError("MMS re-login failed")
    ctx.storage_state(path=str(STATE))
    pg.close()


def main() -> int:
    if not STATE.exists():
        print("FATAL: sessions/mms_state.json missing — run interactive_login --target mms first")
        return 2

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(storage_state=str(STATE), locale="ja-JP",
                            viewport={"width": 1440, "height": 1100},
                            accept_downloads=True)
        page = ctx.new_page()
        page.goto(VALUATION, wait_until="domcontentloaded", timeout=40_000)
        time.sleep(2)
        if "login" in page.url.lower():
            print("session expired → re-login")
            page.close(); _login(ctx); page = ctx.new_page()
            page.goto(VALUATION, wait_until="domcontentloaded", timeout=40_000)
            time.sleep(2)

        shops = page.evaluate(
            r"""() => {const s=document.querySelector("select[name='shop_id']");
                 return s ? [...s.options].map(o=>o.value).filter(v=>v) : []}""")
        if not shops:
            print("FATAL: no shop_id options (page/session problem)")
            page.screenshot(path=str(SESS / "mms_cost_fail.png"))
            ctx.close(); b.close()
            return 4
        print(f"{len(shops)} shops to fetch")

        header: str | None = None
        data_lines: list[str] = []
        ok_shops = 0
        seen_shops: set[str] = set()

        from urllib.parse import quote

        def _decode(b: bytes, enc: str) -> list[str]:
            # Explicit encoding per source path. cp932 is lenient and would
            # silently mojibake UTF-8 bytes, so never "guess" — the caller
            # knows which path produced the bytes.
            try:
                return b.decode(enc).splitlines()
            except UnicodeDecodeError:
                return b.decode("utf-8", "replace").splitlines()

        def fetch_shop(shop: str, idx: int):
            """Two MMS behaviours for ?shop_id=X&do=1:
              • big shops  → returns the CSV directly (octet-stream, cp932)
              • small shops→ returns the HTML list → click CSVとして保存 (utf-8)
            Try the request API first (race-free, no browser download), then
            fall back to the browser client-side export."""
            url = f"{VALUATION}?shop_id={quote(shop)}&item_cd=&do=1"
            # 1) request-API: handles the direct-download big shops cleanly
            try:
                r = ctx.request.get(url, timeout=120_000, headers={"referer": VALUATION})
                cd = (r.headers.get("content-disposition") or "").lower()
                ct = (r.headers.get("content-type") or "").lower()
                body = r.body()
                if (r.status == 200 and ("attachment" in cd or "octet-stream" in ct
                        or body[:40].lstrip().startswith(b'"MMS'))):
                    return _decode(body, "cp932")   # direct-download = Shift-JIS
            except Exception:
                pass
            # 2) browser flow for the HTML-list (small) shops
            pg = ctx.new_page()
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=45_000)
                time.sleep(2)
                rows = pg.evaluate("() => document.querySelectorAll('table tr').length")
                if rows <= 2:
                    return 0
                with pg.expect_download(timeout=40_000) as di:
                    pg.locator("button:has-text('CSVとして保存')").first.click(
                        force=True, no_wait_after=True, timeout=12_000)
                tmp = SESS / f"_mms_{idx}.csv"
                di.value.save_as(str(tmp))
                time.sleep(1.0)
                txt = _decode(tmp.read_bytes(), "utf-8-sig")  # client-side = UTF-8
                tmp.unlink(missing_ok=True)
                return txt if txt else None
            finally:
                pg.close()

        for i, shop in enumerate(shops):
            if shop in seen_shops:
                continue
            got = None
            for attempt in (1, 2, 3):
                try:
                    got = fetch_shop(shop, i)
                    break
                except Exception as exc:
                    if attempt == 3:
                        print(f"  {shop}: skip after 3 tries ({str(exc)[:60]})")
                    else:
                        time.sleep(3)
            if got is None or got == 0:
                if got == 0:
                    seen_shops.add(shop)
                continue
            if header is None:
                header = got[0]
            data_lines.extend(l for l in got[1:] if l.strip())
            ok_shops += 1
            seen_shops.add(shop)
            print(f"  {shop}: +{len(got) - 1} rows")

        ctx.close(); b.close()

        if header is None or not data_lines:
            print("FATAL: no MMS valuation rows collected from any shop")
            return 4

        out = SESS / "評価額一覧-MMS.csv"
        out.write_text("\n".join([header, *data_lines]) + "\n", encoding="utf-8-sig")
        size = out.stat().st_size
        storage.Client().bucket(BUCKET).blob(GCS_PATH).upload_from_filename(str(out))
        print(f"OK: {len(data_lines):,} rows from {ok_shops} shops, "
              f"{size:,} bytes -> gs://{BUCKET}/{GCS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
