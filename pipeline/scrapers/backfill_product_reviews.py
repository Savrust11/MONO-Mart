"""
ZOZO BO 商品レビュー 過去データ一括取得 (バックフィル用)

通常の fetch_product_reviews.py は 1 日ぶん/1 実行。
このスクリプトはブラウザセッションを 1 つ保持したまま日付ループし
最大 1 年分を効率よく取得する。

使い方:
    python backfill_product_reviews.py [start_date] [end_date]
    例: python backfill_product_reviews.py 2025-06-17 2026-06-16

ENV:
    ZOZO_LOGIN_ID / ZOZO_LOGIN_PASSWORD
    ZOZO_BASIC_USER / ZOZO_BASIC_PASSWORD
    GCS_RAW_BUCKET  (default: mono-back-office-system-raw-data)
    HEADLESS        (default: 1)
    SKIP_EXISTING   (default: 1)  -- GCS に既存ファイルがある日付をスキップ
"""
from __future__ import annotations

import csv, io, os, re, sys, time, logging
from datetime import datetime, timedelta, timezone, date as date_cls

from google.cloud import storage
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_reviews")

JST = timezone(timedelta(hours=9))
BASE = "https://to.zozo.jp/to/"
LOGIN_URL = BASE
INIT_URL = BASE + "GoodsReview.asp?c=Init"

BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
HEADLESS = os.getenv("HEADLESS", "1") == "1"
SKIP_EXISTING = os.getenv("SKIP_EXISTING", "1") == "1"

SHOPS = [
    ("MONO-MART",    "1787"),
    ("EMMA CLOTHES", "2031"),
    ("Chaco closet", "2258"),
    ("ADRER",        "2395"),
    ("anown",        "2524"),
    ("Anchor Smith", "2525"),
    ("BONLECILL",    "2710"),
]

CSV_COLUMNS = [
    "review_date", "shop_name", "item_code", "product_code", "product_name",
    "parent_category", "child_category", "rating", "review_title",
    "review_body", "display_status", "reviewer_attr",
]


def _login(page) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()
    logger.info("Login OK: %s", page.url)


def _scrape_shop(page, shop_name: str, shop_id: str,
                 target_date_slash: str) -> list[dict]:
    """Scrape reviews for one shop on one date. Reuses existing logged-in page."""
    page.goto(INIT_URL, wait_until="domcontentloaded", timeout=45_000)
    time.sleep(1.5)

    try:
        page.select_option('select[name="ShopID"]', value=shop_id)
    except Exception as exc:
        logger.warning("  %s: select_option failed: %s", shop_name, exc)

    for input_name in ('ReviewDTFrom', 'ReviewDTTo'):
        try:
            loc = page.locator(f'input[name="{input_name}"]').first
            loc.click(timeout=5_000)
            loc.fill(target_date_slash, timeout=5_000)
            loc.press("Tab", timeout=5_000)
        except Exception as exc:
            logger.warning("  %s: %s set failed: %s", shop_name, input_name, exc)

    try:
        page.locator('input[name="Top"][value="0"]').check(force=True)
    except Exception as exc:
        logger.warning("  %s: check Top=0 failed: %s", shop_name, exc)

    page.evaluate(r"""(args) => {
      try {
        if (window.jQuery) {
          window.jQuery('select[name="ShopID"]').val(args.shopId).trigger('change');
        }
      } catch (e) {}
    }""", {"shopId": shop_id})

    with page.expect_navigation(wait_until="domcontentloaded", timeout=60_000):
        page.locator('button[name="search"][value="SEARCH"]').first.click()
    time.sleep(2)

    body_text = page.evaluate("() => document.body.innerText")
    if "ショップまたは商品情報を指定してください" in body_text:
        return []

    rows: list[dict] = []
    page_idx = 0
    while True:
        page_idx += 1
        time.sleep(1)
        page_rows = page.evaluate(r"""() => {
          const tables = [...document.querySelectorAll('table')];
          let target = null;
          for (const t of tables) {
            const ths = [...t.querySelectorAll('th')].map(
              th => (th.innerText || '').trim());
            const joined = ths.join('|');
            if (/ステータス/.test(joined) && /投稿日/.test(joined)
                && /商品コード/.test(joined)) {
              target = t; break;
            }
          }
          if (!target) return [];
          const out = [];
          const trs = target.querySelectorAll('tbody tr');
          for (const tr of trs) {
            const tds = [...tr.querySelectorAll('td')].map(
              td => (td.innerText || '').replace(/\s+/g,' ').trim());
            if (tds.length < 5) continue;
            if (tds.every(t => !t)) continue;
            out.push(tds);
          }
          return out;
        }""")
        if not page_rows:
            break
        for r in page_rows:
            def at(i, default=""):
                return r[i] if i < len(r) else default
            posted = at(1)
            if posted:
                posted = posted.replace("/", "-")
            rating_raw = at(7)
            rating = None
            if rating_raw:
                m = re.search(r"\d+", rating_raw)
                if m:
                    rating = m.group(0)
                else:
                    rating = str(rating_raw.count("★"))
            rows.append({
                "review_date":     posted or "",
                "shop_name":       at(2),
                "item_code":       at(4),
                "product_code":    at(5),
                "product_name":    "",
                "parent_category": at(3),
                "child_category":  "",
                "rating":          rating or "",
                "review_title":    at(6),
                "review_body":     "",
                "display_status":  at(0),
                "reviewer_attr":   "",
            })

        moved = page.evaluate(r"""(nextNum) => {
          const target = String(nextNum);
          const cand = [...document.querySelectorAll('a, button')];
          for (const c of cand) {
            const disabled = c.getAttribute('disabled') ||
              c.classList.contains('disabled');
            if (disabled) continue;
            const t = (c.innerText || '').trim();
            if (t === target) { c.click(); return true; }
          }
          for (const c of cand) {
            const disabled = c.getAttribute('disabled') ||
              c.classList.contains('disabled');
            if (disabled) continue;
            const t = (c.innerText || '').trim();
            if (t === '次へ' || t === '次の50' || /^>$/.test(t)) {
              c.click(); return true;
            }
          }
          return false;
        }""", page_idx + 1)
        if not moved:
            break
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30_000)
        except Exception:
            pass
        if page_idx >= 30:
            break

    return rows


def _gcs_exists(gcs: storage.Client, date_str: str) -> bool:
    blob = gcs.bucket(BUCKET).blob(
        f"uploads/zozo/reviews/{date_str}/reviews.csv")
    return blob.exists()


def _upload(gcs: storage.Client, date_str: str, all_rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    w.writeheader()
    for r in all_rows:
        w.writerow({k: r.get(k, "") for k in CSV_COLUMNS})
    data = buf.getvalue().encode("utf-8-sig")
    gcs_key = f"uploads/zozo/reviews/{date_str}/reviews.csv"
    gcs.bucket(BUCKET).blob(gcs_key).upload_from_string(
        data, content_type="text/csv; charset=utf-8")
    logger.info("  uploaded gs://%s/%s (%d rows)", BUCKET, gcs_key, len(all_rows))


def _date_range(start: str, end: str):
    d = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    while d <= e:
        yield d.isoformat()
        d += timedelta(days=1)


def main() -> int:
    start_date = sys.argv[1] if len(sys.argv) > 1 else "2025-06-17"
    end_date = sys.argv[2] if len(sys.argv) > 2 else (
        datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info("Backfill reviews: %s .. %s (SKIP_EXISTING=%s)",
                start_date, end_date, SKIP_EXISTING)

    if not os.getenv("ZOZO_LOGIN_ID") or not os.getenv("ZOZO_BASIC_USER"):
        logger.error("FATAL: ZOZO credentials missing in env")
        return 2

    gcs = storage.Client()
    dates = list(_date_range(start_date, end_date))
    logger.info("Total dates to process: %d", len(dates))

    ok_count = 0
    skip_count = 0
    fail_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            ctx = browser.new_context(
                locale="ja-JP", viewport={"width": 1440, "height": 1100},
                http_credentials={
                    "username": os.environ["ZOZO_BASIC_USER"],
                    "password": os.environ["ZOZO_BASIC_PASSWORD"],
                },
            )
            page = ctx.new_page()
            _login(page)

            for date_str in dates:
                if SKIP_EXISTING and _gcs_exists(gcs, date_str):
                    logger.info("[%s] SKIP (already in GCS)", date_str)
                    skip_count += 1
                    continue

                logger.info("[%s] Scraping ...", date_str)
                target_slash = date_str.replace("-", "/")
                all_rows: list[dict] = []
                date_ok = True

                for shop_name, shop_id in SHOPS:
                    try:
                        rows = _scrape_shop(page, shop_name, shop_id, target_slash)
                        for r in rows:
                            if not r["review_date"]:
                                r["review_date"] = date_str
                        all_rows.extend(rows)
                        logger.info("  [%s] %s: %d rows", date_str, shop_name, len(rows))
                    except Exception as exc:
                        logger.warning("  [%s] %s FAILED: %s", date_str, shop_name, exc)
                        date_ok = False

                if all_rows:
                    try:
                        _upload(gcs, date_str, all_rows)
                        ok_count += 1
                    except Exception as exc:
                        logger.error("  [%s] GCS upload failed: %s", date_str, exc)
                        fail_count += 1
                elif date_ok:
                    logger.info("  [%s] No reviews found — skipping GCS upload", date_str)
                    ok_count += 1
                else:
                    fail_count += 1

                time.sleep(3)
        finally:
            browser.close()

    logger.info(
        "Backfill complete: ok=%d  skip=%d  fail=%d",
        ok_count, skip_count, fail_count,
    )
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
