"""
ZOZO BO ファーストセラー 過去データ一括取得 (バックフィル用)

通常の fetch_first_seller.py は 1 週分/1 実行。
このスクリプトはブラウザセッションを 1 つ保持したまま週ループし
52 週分を効率よく取得する。

使い方:
    python backfill_first_seller.py [start_monday] [end_monday]
    例: python backfill_first_seller.py 2025-06-23 2026-06-16

    start_monday: 最初の TARGET_DATE (月曜) — iso_previous_week() でその前週を取得
    end_monday  : 最後の TARGET_DATE (月曜)  (default: 直近の月曜)

    52W 1W目 (週開始 2025-06-16) を取得するには start_monday=2025-06-23 を指定。

ENV:
    ZOZO_LOGIN_ID / ZOZO_LOGIN_PASSWORD
    ZOZO_BASIC_USER / ZOZO_BASIC_PASSWORD
    GCS_RAW_BUCKET  (default: mono-back-office-system-raw-data)
    HEADLESS        (default: 1)
    SKIP_EXISTING   (default: 1)  -- GCS に既存ファイルがある週をスキップ
"""
from __future__ import annotations

import csv, io, os, sys, time, logging
from datetime import date, datetime, timedelta, timezone

from google.cloud import storage
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_first_seller")

JST = timezone(timedelta(hours=9))
BASE = "https://to.zozo.jp/to/"
LOGIN_URL = BASE
PAGE_URL = BASE + "siteinfo.asp?c=Seller&clear=on"

BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
HEADLESS = os.getenv("HEADLESS", "1") == "1"
SKIP_EXISTING = os.getenv("SKIP_EXISTING", "1") == "1"

GENDERS = [("MEN", "1"), ("WOMEN", "2")]


def iso_previous_week(today: date) -> tuple[date, date]:
    monday_this = today - timedelta(days=today.isoweekday() - 1)
    sunday_prev = monday_this - timedelta(days=1)
    monday_prev = sunday_prev - timedelta(days=6)
    return monday_prev, sunday_prev


def _most_recent_monday() -> date:
    today = datetime.now(JST).date()
    return today - timedelta(days=today.isoweekday() - 1)


def _mondays_in_range(start: date, end: date) -> list[date]:
    out = []
    d = start - timedelta(days=start.isoweekday() - 1)  # snap to Monday
    while d <= end:
        out.append(d)
        d += timedelta(weeks=1)
    return out


def _login(page) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()
    logger.info("Login OK: %s", page.url)


def _search_and_scrape(page, mon: date, sun: date,
                       gender_label: str, gender_id: str) -> list[list[str]]:
    page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=45_000)
    time.sleep(5)

    from_str = mon.strftime("%Y/%m/%d")
    to_str = sun.strftime("%Y/%m/%d")
    page.fill('input[name="SellTermDTFrom"]', from_str)
    page.fill('input[name="SellTermDTTo"]', to_str)

    page.evaluate(f"""() => {{
      const r = document.querySelector(
        'input[name="CustomerTypeID"][value="{gender_id}"]');
      if (r) {{ r.checked = true; r.dispatchEvent(new Event('change', {{bubbles:true}})); }}
    }}""")
    page.evaluate("""() => {
      const r = document.querySelector('input[name="SellOrderBy"][value="1"]');
      if (r) { r.checked = true; }
    }""")
    page.evaluate("""() => {
      const s = document.querySelector('select[name="ShopID"]');
      if (s) { s.value = ''; s.dispatchEvent(new Event('change',{bubbles:true})); }
    }""")

    time.sleep(1)
    btn = page.locator('button[name="search"][value="SEARCH"]')
    if btn.count() == 0:
        raise RuntimeError("検索ボタンが見つかりません")
    btn.first.click(timeout=10_000)
    page.wait_for_load_state("domcontentloaded", timeout=60_000)
    time.sleep(8)

    rows = page.evaluate(r"""() => {
      const norm = s => (s==null?'':String(s)).replace(/\s+/g,' ').trim();
      const tables = [...document.querySelectorAll('table')];
      let best = null, bestRows = 0;
      for (const t of tables) {
        const n = t.querySelectorAll('tr').length;
        if (n > bestRows) { best = t; bestRows = n; }
      }
      if (!best) return [];
      return [...best.querySelectorAll('tr')].map(tr =>
        [...tr.querySelectorAll('th,td')].map(c => norm(c.innerText || ''))
      );
    }""")
    return rows


def _gcs_exists(gcs: storage.Client, target_date: date, iso_week: int) -> bool:
    blob = gcs.bucket(BUCKET).blob(
        f"uploads/zozo/first_seller/{target_date.isoformat()}/"
        f"first_seller_W{iso_week:02d}.csv")
    return blob.exists()


def _upload(gcs: storage.Client, target_date: date, iso_week: int,
            all_results: list[list[str]]) -> None:
    buf = io.StringIO()
    csv.writer(buf).writerows(all_results)
    data = buf.getvalue().encode("utf-8-sig")
    gcs_path = (f"uploads/zozo/first_seller/{target_date.isoformat()}/"
                f"first_seller_W{iso_week:02d}.csv")
    gcs.bucket(BUCKET).blob(gcs_path).upload_from_string(
        data, content_type="text/csv")
    logger.info("  uploaded gs://%s/%s (%d data rows)",
                BUCKET, gcs_path, len(all_results) - 1)


def main() -> int:
    today_jst = datetime.now(JST).date()

    if len(sys.argv) > 1:
        start_monday = date.fromisoformat(sys.argv[1])
    else:
        start_monday = today_jst - timedelta(weeks=52)
        start_monday -= timedelta(days=start_monday.isoweekday() - 1)

    if len(sys.argv) > 2:
        end_monday = date.fromisoformat(sys.argv[2])
    else:
        end_monday = _most_recent_monday()

    mondays = _mondays_in_range(start_monday, end_monday)
    logger.info("Backfill first_seller: %s .. %s (%d weeks, SKIP_EXISTING=%s)",
                start_monday, end_monday, len(mondays), SKIP_EXISTING)

    if not os.getenv("ZOZO_LOGIN_ID") or not os.getenv("ZOZO_BASIC_USER"):
        logger.error("FATAL: ZOZO credentials missing")
        return 2

    gcs = storage.Client()
    ok_count = skip_count = fail_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            ctx = browser.new_context(
                locale="ja-JP", viewport={"width": 1600, "height": 1100},
                accept_downloads=True,
                http_credentials={
                    "username": os.environ["ZOZO_BASIC_USER"],
                    "password": os.environ["ZOZO_BASIC_PASSWORD"],
                },
            )
            pg = ctx.new_page()
            _login(pg)

            for target_monday in mondays:
                mon, sun = iso_previous_week(target_monday)
                cal = mon.isocalendar()
                iso_year, iso_week = cal.year, cal.week

                if SKIP_EXISTING and _gcs_exists(gcs, target_monday, iso_week):
                    logger.info("[%s] SKIP W%02d (already in GCS)",
                                target_monday, iso_week)
                    skip_count += 1
                    continue

                logger.info("[%s] Fetching W%02d (%s ~ %s) ...",
                            target_monday, iso_week, mon, sun)

                all_results: list[list[str]] = []
                header_added = False
                week_ok = True

                for gender_label, gender_id in GENDERS:
                    try:
                        rows = _search_and_scrape(pg, mon, sun,
                                                  gender_label, gender_id)
                        if not rows:
                            logger.warning("  W%02d %s: empty result",
                                           iso_week, gender_label)
                            continue

                        kept_cols = [i for i in range(len(rows[0]))
                                     if rows[0][i].strip() != ""]
                        rows = [[r[i] if i < len(r) else "" for i in kept_cols]
                                for r in rows]
                        header_row = rows[0]
                        if not header_added:
                            all_results.append(
                                ["iso_year", "iso_week", "period_from",
                                 "period_to", "gender"] + header_row)
                            header_added = True
                        data_rows = [r for r in rows[1:] if r != header_row]
                        for r in data_rows:
                            all_results.append(
                                [str(iso_year), str(iso_week), mon.isoformat(),
                                 sun.isoformat(), gender_label] + r)
                        logger.info("  W%02d %s: %d rows",
                                    iso_week, gender_label, len(data_rows))
                    except Exception as exc:
                        logger.warning("  W%02d %s FAILED: %s",
                                       iso_week, gender_label, exc)
                        week_ok = False

                if len(all_results) > 1:
                    try:
                        _upload(gcs, target_monday, iso_week, all_results)
                        ok_count += 1
                    except Exception as exc:
                        logger.error("  W%02d GCS upload failed: %s", iso_week, exc)
                        fail_count += 1
                elif week_ok:
                    logger.info("  W%02d: no data scraped", iso_week)
                    ok_count += 1
                else:
                    fail_count += 1

                time.sleep(5)
        finally:
            browser.close()

    logger.info("Backfill complete: ok=%d  skip=%d  fail=%d",
                ok_count, skip_count, fail_count)
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
