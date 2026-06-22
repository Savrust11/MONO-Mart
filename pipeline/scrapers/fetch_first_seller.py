"""
ZOZO BO ファーストセラー (No.16) — 週次取得。

クライアント仕様 (2026-05-29 確定):
  ・期間: ISO 8601 週 (月曜〜日曜)。毎週月曜03:00 JSTに前週分を取得。
  ・ショップ: ZOZOTOWN全店 (ShopID=0)
  ・親カテゴリ: 指定なし (SCategoryPID=0)
  ・商品タイプ × タイプ: 全てを1つずつループ (将来拡張)
  ・性別: MEN (CustomerTypeID=1), WOMEN (CustomerTypeID=2) それぞれ
  ・販売タイプ: 指定なし (OrderType=0)
  ・価格タイプ: 指定なし (PriceType=0)
  ・並び: 売上順 (SellOrderBy=1)
  ・モール: 指定なし (MallCheck=0)

ZOZO BO ファーストセラーは DL不可なため、画面表示の TOP50 ランキング
テーブルを HTML スクレイピングし CSV に整形してGCSへ保存する方式。

URL: https://to.zozo.jp/to/siteinfo.asp?c=Seller&clear=on
Form: form1 POST siteinfo.asp (c=Seller)

ENV:
  ZOZO_LOGIN_ID / ZOZO_LOGIN_PASSWORD / ZOZO_BASIC_USER / ZOZO_BASIC_PASSWORD
  GCS_RAW_BUCKET   (default: mono-back-office-system-raw-data)
  TARGET_DATE      (default: today JST; ISO週 = TARGET_DATE を含む週の前週)
"""
from __future__ import annotations
import csv, io, os, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from google.cloud import storage
from playwright.sync_api import sync_playwright

JST = timezone(timedelta(hours=9))
BASE = "https://to.zozo.jp/to/"
LOGIN_URL = BASE
PAGE_URL = BASE + "siteinfo.asp?c=Seller&clear=on"

# Gender axis to loop. CustomerTypeID: 0=指定なし, 1=MEN, 2=WOMEN, 3=KIDS
GENDERS = [
    ("MEN",   "1"),
    ("WOMEN", "2"),
]


def iso_previous_week(today: date) -> tuple[date, date]:
    """Return (Monday, Sunday) of the ISO week PRIOR to `today`.

    ISO 8601: week starts Monday. If today is Sunday 2026/06/14, returns
    (2026/06/01, 2026/06/07).
    """
    monday_this_week = today - timedelta(days=today.isoweekday() - 1)
    sunday_prev_week = monday_this_week - timedelta(days=1)
    monday_prev_week = sunday_prev_week - timedelta(days=6)
    return monday_prev_week, sunday_prev_week


def iso_week_number(d: date) -> tuple[int, int]:
    """Return (iso_year, iso_week) for date d. e.g. 2026/06/01 → (2026, 23)."""
    cal = d.isocalendar()
    return cal.year, cal.week


def login(page) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()


def search_and_scrape(page, mon: date, sun: date, gender_label: str,
                      gender_id: str) -> list[list[str]]:
    """Run the search with given filters and scrape the result table.

    Returns: list of rows including header (first row).
    """
    page.goto(PAGE_URL, wait_until="domcontentloaded", timeout=45_000)
    time.sleep(5)

    # Fill date range (datepicker inputs accept YYYY/MM/DD)
    from_str = mon.strftime("%Y/%m/%d")
    to_str = sun.strftime("%Y/%m/%d")
    page.fill('input[name="SellTermDTFrom"]', from_str)
    page.fill('input[name="SellTermDTTo"]', to_str)

    # Select gender (radio)
    page.evaluate(f"""() => {{
      const r = document.querySelector(
        'input[name="CustomerTypeID"][value="{gender_id}"]');
      if (r) {{ r.checked = true; r.dispatchEvent(new Event('change', {{bubbles:true}})); }}
    }}""")

    # Order: 売上 (already default = 1) — make explicit
    page.evaluate("""() => {
      const r = document.querySelector('input[name="SellOrderBy"][value="1"]');
      if (r) { r.checked = true; }
    }""")

    # ShopID: 全店 = "0" (no specific shop)
    page.evaluate("""() => {
      const s = document.querySelector('select[name="ShopID"]');
      if (s) { s.value = ''; s.dispatchEvent(new Event('change',{bubbles:true})); }
    }""")

    time.sleep(1)
    # Click 検索 (the page's own submit button, not header search).
    # Header has its own submit button without a name attribute; the page
    # form1 button is button[name="search"][value="SEARCH"].
    btn = page.locator('button[name="search"][value="SEARCH"]')
    if btn.count() == 0:
        raise RuntimeError("検索ボタンが見つかりません")
    btn.first.click(timeout=10_000)
    # networkidle on ZOZO BO can hang due to background analytics; use
    # domcontentloaded + manual wait instead.
    page.wait_for_load_state("domcontentloaded", timeout=60_000)
    time.sleep(8)

    # Scrape the ranking table
    rows = page.evaluate(r"""() => {
      const norm = s => (s==null?'':String(s)).replace(/\s+/g,' ').trim();
      // Find the main result table — usually the largest <table>
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


def main():
    target_date_str = os.getenv("TARGET_DATE")
    if target_date_str:
        target_date = date.fromisoformat(target_date_str)
    else:
        target_date = datetime.now(JST).date()

    mon, sun = iso_previous_week(target_date)
    iso_year, iso_week = iso_week_number(mon)
    bucket_name = os.getenv("GCS_RAW_BUCKET",
                            "mono-back-office-system-raw-data")

    print(f"target_date  : {target_date}")
    print(f"ISO week     : {iso_year}-W{iso_week:02d}")
    print(f"period       : {mon} (月) 〜 {sun} (日)")

    with sync_playwright() as p:
        b = p.chromium.launch(headless=os.getenv("HEADLESS", "1") == "1")
        ctx = b.new_context(
            locale="ja-JP", viewport={"width": 1600, "height": 1100},
            accept_downloads=True,
            http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                              "password": os.environ["ZOZO_BASIC_PASSWORD"]})
        pg = ctx.new_page()
        login(pg)
        print(f"logged in: {pg.url}")

        all_results = []
        header_added = False
        for gender_label, gender_id in GENDERS:
            print(f"\n--- 検索: 性別={gender_label} 期間={mon}〜{sun} ---")
            try:
                rows = search_and_scrape(pg, mon, sun, gender_label, gender_id)
                if not rows:
                    print(f"  ⚠ empty result for {gender_label}")
                    continue
                # Strip empty columns (e.g. checkbox column with no header).
                def _strip(row):
                    return [c for i, c in enumerate(row)
                            if rows[0][i].strip() != "" or
                               any(r[i].strip() != "" for r in rows if i < len(r))]
                kept_cols = [i for i in range(len(rows[0]))
                             if rows[0][i].strip() != ""]
                rows = [[r[i] if i < len(r) else "" for i in kept_cols]
                        for r in rows]

                header_row = rows[0]  # ['ショップ', '親カテ', 'ブランド品番', ...]
                if not header_added:
                    all_results.append(
                        ["iso_year", "iso_week", "period_from",
                         "period_to", "gender"] + header_row)
                    header_added = True
                # Skip any row that equals the header row (some pages render
                # the header twice — once in thead, once as the first tbody row).
                data_rows = [r for r in rows[1:] if r != header_row]
                for r in data_rows:
                    all_results.append(
                        [str(iso_year), str(iso_week), mon.isoformat(),
                         sun.isoformat(), gender_label] + r)
                print(f"  ✓ {gender_label}: {len(data_rows)} ranking rows scraped")
            except Exception as e:
                print(f"  ✗ {gender_label} FAILED: {str(e)[:200]}")

        ctx.close(); b.close()

    if not all_results:
        print("no data scraped")
        return 1

    # Write CSV
    buf = io.StringIO()
    csv.writer(buf).writerows(all_results)
    data = buf.getvalue().encode("utf-8-sig")

    gcs_path = (f"uploads/zozo/first_seller/{target_date.isoformat()}/"
                f"first_seller_W{iso_week:02d}.csv")
    storage.Client().bucket(bucket_name).blob(gcs_path).upload_from_string(
        data, content_type="text/csv")
    print(f"\n✓ saved: gs://{bucket_name}/{gcs_path} "
          f"({len(all_results)-1} rows × {len(GENDERS)} genders, "
          f"{len(data):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
