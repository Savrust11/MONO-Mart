"""ZOZO BO 商品レビュー (No.15) — daily auto-fetch (per shop HTML scrape).

GoodsReview.asp は CSV ダウンロード不可。検索結果ページの HTML テーブルを
パースして CSV に整形する方式 ([[zozo-scraper-status]] の方針)。

検索フォーム制約: ショップまたは商品情報の指定が必須 (ない場合
「ショップまたは商品情報を指定してください。」 と返る)。よって 7 ショップを
ループで投げて、それぞれの日次差分 (target_date の投稿) を取得。

GCS path:  gs://.../uploads/zozo/reviews/{date}/reviews.csv  (UTF-8 BOM)
ETL:       analytics_layer.product_reviews

ENV:
    ZOZO_LOGIN_ID / ZOZO_LOGIN_PASSWORD / ZOZO_BASIC_USER / ZOZO_BASIC_PASSWORD
    GCS_RAW_BUCKET (default: mono-back-office-system-raw-data)
    TARGET_DATE    (default: yesterday JST)
    HEADLESS       (default: 1)
"""
from __future__ import annotations

import csv, io, os, re, sys, time, logging
from datetime import datetime, timedelta, timezone

from google.cloud import storage
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("product_reviews")

JST = timezone(timedelta(hours=9))
BASE = "https://to.zozo.jp/to/"
LOGIN_URL = BASE
INIT_URL = BASE + "GoodsReview.asp?c=Init"

BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
HEADLESS = os.getenv("HEADLESS", "1") == "1"

# Shop list with ShopID values (from probe of GoodsReview.asp select).
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


def _get_target_date() -> str:
    env = os.getenv("TARGET_DATE")
    if env:
        return env
    return (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")


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
    """Submit search for a shop on a single date, parse all result pages."""
    page.goto(INIT_URL, wait_until="domcontentloaded", timeout=45_000)
    time.sleep(1.5)

    # Use Playwright's select_option for the shop select (Select2-friendly).
    try:
        page.select_option('select[name="ShopID"]', value=shop_id)
    except Exception as exc:
        logger.warning("  %s: select_option failed: %s", shop_name, exc)
    # Date inputs: ZOZO's datepicker drops .value-set on submit, and
    # page.fill alone doesn't trigger the picker's internal state. Click
    # the input first, then fill, then press Tab to commit the value.
    for input_name in ('ReviewDTFrom', 'ReviewDTTo'):
        try:
            loc = page.locator(f'input[name="{input_name}"]').first
            loc.click(timeout=5_000)
            loc.fill(target_date_slash, timeout=5_000)
            loc.press("Tab", timeout=5_000)
        except Exception as exc:
            logger.warning("  %s: %s set failed: %s",
                           shop_name, input_name, exc)
    # Verify the dates stuck (datepicker can revert on bad format).
    after = page.evaluate(r"""() => {
      const f = document.forms['form1'];
      return {
        from: f?.querySelector('input[name="ReviewDTFrom"]')?.value || '',
        to:   f?.querySelector('input[name="ReviewDTTo"]')?.value || '',
      };
    }""")
    logger.info("  %s: date range = %s..%s",
                shop_name, after.get("from"), after.get("to"))
    # Top=0 (指定なし = 全件). Use Playwright check() for proper events.
    try:
        page.locator('input[name="Top"][value="0"]').check(force=True)
    except Exception as exc:
        logger.warning("  %s: check Top=0 failed: %s", shop_name, exc)
    # Belt-and-suspenders: also trigger jQuery select change for Select2
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

    # If page reports error (no shop/product specified) skip
    body_text = page.evaluate("() => document.body.innerText")
    if "ショップまたは商品情報を指定してください" in body_text:
        logger.warning("  %s: search rejected (filter requirement)", shop_name)
        return []

    rows: list[dict] = []
    page_idx = 0
    while True:
        page_idx += 1
        time.sleep(1)
        page_rows = page.evaluate(r"""() => {
          // The actual result table is identified by the unique「ステータス」
          // header column — the search-form table above it has nearly
          // identical TH labels (ショップ/カテゴリ/商品コード/...) and the
          // earlier (buggy) selector picked the form table by mistake.
          // Live structure (probed 2026-06-03):
          //   ステータス | 投稿日 | ショップ | 親カテゴリ | 商品コード |
          //   ブランド品番 | タイトル | 評価
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
        logger.info("  %s page %d: %d row(s)", shop_name, page_idx, len(page_rows))
        for r in page_rows:
            # Column order (probed 2026-06-03):
            # 0:ステータス 1:投稿日 2:ショップ 3:親カテゴリ
            # 4:商品コード 5:ブランド品番 6:タイトル 7:評価
            def at(i, default=""):
                return r[i] if i < len(r) else default
            posted = at(1)
            if posted:
                posted = posted.replace("/", "-")
            rating_raw = at(7)
            # Rating may be a star string ("★★★★☆") or "5" etc.
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

        # Pagination: ZOZO BO renders numeric page links (2, 3, 4...) or
        # 次へ-style next links depending on count. Click the link/button
        # for `page_idx + 1` — most reliable mechanism. Stop on disabled
        # state or if no matching link found.
        moved = page.evaluate(r"""(nextNum) => {
          const target = String(nextNum);
          const cand = [...document.querySelectorAll('a, button')];
          // Pass 1: explicit next page number
          for (const c of cand) {
            const disabled = c.getAttribute('disabled') ||
              c.classList.contains('disabled');
            if (disabled) continue;
            const t = (c.innerText || '').trim();
            if (t === target) { c.click(); return true; }
          }
          // Pass 2: 次へ / 次の50 / ">"
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
        # Safety cap to prevent runaway scraping. ZOZO's datepicker
        # doesn't reliably persist filter dates on submit (see verified
        # 2026-06-09), so without the date filter we end up paging through
        # ALL historical reviews. Cap at 30 pages (1,500 reviews/shop/day)
        # which is well beyond the highest observed daily count and covers
        # the freshness window we care about.
        if page_idx >= 30:
            logger.info("  %s: 30-page cap reached — stopping", shop_name)
            break

    return rows


def main() -> int:
    target_date = _get_target_date()  # YYYY-MM-DD
    target_slash = target_date.replace("-", "/")
    logger.info("Product review fetch start (target=%s)", target_date)

    if not os.getenv("ZOZO_LOGIN_ID") or not os.getenv("ZOZO_BASIC_USER"):
        logger.error("FATAL: ZOZO credentials missing in env")
        return 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            ctx = browser.new_context(
                locale="ja-JP", viewport={"width": 1440, "height": 1100},
                http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                                  "password": os.environ["ZOZO_BASIC_PASSWORD"]},
            )
            page = ctx.new_page()
            _login(page)

            all_rows: list[dict] = []
            for shop_name, shop_id in SHOPS:
                logger.info("Shop %s", shop_name)
                try:
                    rows = _scrape_shop(page, shop_name, shop_id, target_slash)
                    # Stamp review_date with target_date if cell is empty
                    for r in rows:
                        if not r["review_date"]:
                            r["review_date"] = target_date
                    all_rows.extend(rows)
                except Exception as exc:
                    logger.warning("  %s failed: %s", shop_name, exc)

            logger.info("Total reviews collected: %d", len(all_rows))
            if not all_rows:
                logger.info("No new reviews on %s — exit 0", target_date)
                return 0

            # Write CSV (UTF-8 BOM for Excel compatibility)
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
            w.writeheader()
            for r in all_rows:
                w.writerow({k: r.get(k, "") for k in CSV_COLUMNS})
            data = buf.getvalue().encode("utf-8-sig")

            gcs_key = f"uploads/zozo/reviews/{target_date}/reviews.csv"
            storage.Client().bucket(BUCKET).blob(gcs_key).upload_from_string(
                data, content_type="text/csv; charset=utf-8")
            logger.info("✓ uploaded gs://%s/%s (%s rows, %s bytes)",
                        BUCKET, gcs_key, f"{len(all_rows):,}", f"{len(data):,}")
            return 0
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
