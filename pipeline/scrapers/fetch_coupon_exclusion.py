"""ZOZO BO クーポン除外 (No.18) — daily auto-fetch.

実際のフロー (2026-06-01 ライブ確認):
  1. EventCalendar.asp?c=DispCalendar → 「クーポン情報」テーブルに今後のクーポン
     実施予定一覧 (実施日 × ショップ × 詳細確認リンク)
  2. 各行の「詳細確認」 → ShopCoupon.asp?c=DispDetailSchedule&DT=YYYY/MM/DD
  3. 詳細ページに per-brand「ダウンロード」リンク
       ?c=NonTargetList&CouponScheduleID=NNNNNN&ShopName=BRAND&DT=YYYY/M/D
     → cp932 CSV (商品コード, ブランド品番, 除外フラグ等)

クーポン除外設定はクーポン実施前々日 23:59 までに行うため、毎日「カレンダーに
出ているすべての近未来クーポン分」を取得して上書きする方式 (常に最新確定状態
を保持)。クーポン無しの日は no-op で正常終了。

GCS path: gs://.../uploads/zozo/coupon/{event_date}/{ShopName}_{YYYYMMDD}.csv
ETL:      analytics_layer.coupon_exclusion (csv_coupon_exclusion @ main.py:370)

ENV:
    ZOZO_LOGIN_ID / ZOZO_LOGIN_PASSWORD / ZOZO_BASIC_USER / ZOZO_BASIC_PASSWORD
    GCS_RAW_BUCKET   (default: mono-back-office-system-raw-data)
    HEADLESS         (default: 1)
"""
from __future__ import annotations

import os, re, sys, time, logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urljoin, urlencode, quote

from google.cloud import storage
from playwright.sync_api import sync_playwright, BrowserContext, Page

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("coupon_exclusion")

JST = timezone(timedelta(hours=9))
BASE = "https://to.zozo.jp/to/"
LOGIN_URL = BASE
EVENT_CAL = BASE + "EventCalendar.asp?c=DispCalendar"
SHOP_COUPON = BASE + "ShopCoupon.asp"

BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
HEADLESS = os.getenv("HEADLESS", "1") == "1"

EXPECTED_HEADER_MARKER = "商品コード"  # cp932 header signal


def _looks_like_coupon_csv(data: bytes) -> bool:
    if len(data) < 30:
        return False
    head_lower = data[:300].lower()
    if b"<html" in head_lower or b"<!doctype" in head_lower:
        return False
    try:
        sample = data[:600].decode("cp932", errors="replace")
    except Exception:
        return False
    return EXPECTED_HEADER_MARKER in sample


def _login(page: Page) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()
    logger.info("Login OK: %s", page.url)


def _discover_coupon_schedules(page: Page) -> list[dict]:
    """EventCalendar から今後のクーポン実施日一覧を抽出。

    Returns: list of {detail_url, event_date_iso, raw_date} dicts.
    """
    page.goto(EVENT_CAL, wait_until="domcontentloaded", timeout=45_000)
    time.sleep(2)

    rows = page.evaluate(r"""() => {
      const out = [];
      // The schedule table is the first table inside #content with a
      // 「詳細確認」 link in each row.
      for (const a of document.querySelectorAll('a[href*="ShopCoupon.asp"][href*="DispDetailSchedule"]')) {
        const href = a.getAttribute('href') || '';
        const row = a.closest('tr');
        const dateCell = row ? row.querySelector('td') : null;
        const dateText = dateCell ? (dateCell.innerText || '').trim() : '';
        const m = dateText.match(/(\d{4})\/(\d{1,2})\/(\d{1,2})/);
        const iso = m ? `${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}` : null;
        out.push({href, raw_date: dateText, iso});
      }
      return out;
    }""")

    schedules: list[dict] = []
    seen = set()
    for r in rows:
        full = urljoin(EVENT_CAL, r["href"])
        if full in seen or not r.get("iso"):
            continue
        seen.add(full)
        schedules.append({"detail_url": full,
                          "event_date_iso": r["iso"],
                          "raw_date": r["raw_date"]})

    logger.info("Discovered %d upcoming coupon schedule(s)", len(schedules))
    for s in schedules:
        logger.info("  - %s (%s)", s["event_date_iso"], s["raw_date"])
    return schedules


def _discover_brand_downloads(page: Page, detail_url: str) -> list[dict]:
    """Detail page → per-brand ダウンロード anchors.

    URL pattern: ShopCoupon.asp?c=NonTargetList&CouponScheduleID=N&ShopName=B&DT=D
    """
    page.goto(detail_url, wait_until="domcontentloaded", timeout=45_000)
    time.sleep(2)

    anchors = page.evaluate(r"""() => {
      const out = [];
      // Brand rows have a "ダウンロード" anchor with NonTargetList query.
      for (const a of document.querySelectorAll('a[href*="NonTargetList"]')) {
        const href = a.getAttribute('href') || '';
        const row = a.closest('tr');
        let shopName = '';
        if (row) {
          // ShopName is in the second <td> typically (after shopid). Get all <td>s.
          const tds = [...row.querySelectorAll('td')];
          // Use the cell whose text matches a known shop format; pick the
          // longest non-numeric td as a heuristic, but also expose the row
          // text for the caller to extract from href as authoritative.
          shopName = tds.length >= 2 ? (tds[1].innerText || '').trim() : '';
        }
        out.push({href, row_shop: shopName});
      }
      return out;
    }""")
    return anchors


SHOP_NAME_FROM_HREF = re.compile(r"ShopName=([^&]+)", re.IGNORECASE)
COUPON_ID_FROM_HREF = re.compile(r"CouponScheduleID=(\d+)", re.IGNORECASE)


def _fetch_brand_csv(
    context: BrowserContext, detail_url: str, dl_href: str
) -> tuple[Optional[bytes], Optional[str]]:
    """Resolve the relative dl href, GET with auth, return (bytes, brand)."""
    full = urljoin(detail_url, dl_href)
    m = SHOP_NAME_FROM_HREF.search(full)
    brand = None
    if m:
        from urllib.parse import unquote_plus
        brand = unquote_plus(m.group(1))
    try:
        r = context.request.get(full, timeout=120_000, headers={"referer": detail_url})
        if r.status != 200:
            logger.warning("    HTTP %d for %s", r.status, full[:120])
            return None, brand
        return r.body(), brand
    except Exception as exc:
        logger.warning("    GET failed %s: %s", full[:120], exc)
        return None, brand


def main() -> int:
    logger.info("Coupon exclusion fetch start (now=%s)", datetime.now(JST).isoformat())

    if not os.getenv("ZOZO_LOGIN_ID") or not os.getenv("ZOZO_BASIC_USER"):
        logger.error("FATAL: ZOZO credentials missing in env")
        return 2

    bucket = storage.Client().bucket(BUCKET)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            context = browser.new_context(
                locale="ja-JP", viewport={"width": 1440, "height": 1100},
                http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                                  "password": os.environ["ZOZO_BASIC_PASSWORD"]},
                accept_downloads=True,
            )
            page = context.new_page()
            _login(page)

            schedules = _discover_coupon_schedules(page)
            if not schedules:
                logger.info("No upcoming coupon schedules on EventCalendar — exit 0")
                return 0

            uploaded = 0
            for sch in schedules:
                event_date = sch["event_date_iso"]
                yyyymmdd = event_date.replace("-", "")
                logger.info("Inspecting schedule %s", event_date)
                dl_cands = _discover_brand_downloads(page, sch["detail_url"])
                if not dl_cands:
                    logger.info("  (no brand download anchors — skip)")
                    continue

                for c in dl_cands:
                    data, brand = _fetch_brand_csv(context, sch["detail_url"], c["href"])
                    if not data:
                        continue
                    if not _looks_like_coupon_csv(data):
                        logger.warning("    %s: not a coupon CSV (got %d bytes, head=%r)",
                                       brand or "?", len(data), data[:80])
                        continue
                    if not brand:
                        brand = c.get("row_shop") or "UNKNOWN"
                    filename = f"{brand}_{yyyymmdd}.csv"
                    gcs_key = f"uploads/zozo/coupon/{event_date}/{filename}"
                    bucket.blob(gcs_key).upload_from_string(
                        data, content_type="text/csv; charset=shift_jis")
                    logger.info("    ✓ %s → gs://%s/%s (%s bytes)",
                                brand, BUCKET, gcs_key, f"{len(data):,}")
                    uploaded += 1

            logger.info("Coupon exclusion fetch done: %d brand CSVs uploaded "
                        "across %d schedules", uploaded, len(schedules))
            return 0
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
