"""ZOZO BO ZOZOAD レポート 4種類CSV (No.7) — daily auto-fetch + 失敗時リトライ対応。

クライアント要件 (2026-06):
  ・画面右側の「4種類」の詳細CSVをそれぞれ取得する:
      日別CSV          c=DailyCSVDownLoad      type=shop
      品番別CSV        c=GoodsInfoCSVDownLoad  type=brandcode
      アップロード品番CSV c=UploadGoodsCSVDownLoad type=goodslist
      詳細CSV          c=DetailCSVDownLoad     type=brandcode
  ・リトライスケジュール (12:30→13:30→14:30→15:30→18:00→翌7:00):
      ZOZO広告実績は日中に順次反映されるため、データが出る(=非空CSV)まで
      時間をずらして再取得。1度成功したら以降はスキップ。
      → 成功マーカー gs://.../uploads/zozo/zozoad/_success/{run_date}.done で制御。
      → タスクスケジューラに6トリガー登録 (setup_zozoad_schedule.ps1)。

ShopID=-1 では取得不可なため per-shop GET をループ → 種類ごとに1ファイルへ統合。
GCS: gs://.../uploads/zozo/zozoad/{fetch_date}/{name}.csv
ETL: 品番別(Detail.csv)のみ analytics_layer.zozoad_daily へ (既存)。他3種は生CSV保管。

ENV: ZOZO_LOGIN_ID/PASSWORD, ZOZO_BASIC_USER/PASSWORD, GCS_RAW_BUCKET,
     TARGET_DATE, ZOZOAD_LAG_DAYS(=1), HEADLESS(=1), FORCE(=0 で成功済みでも再取得)
"""
from __future__ import annotations

import os, sys, time, logging
from datetime import datetime, timedelta, timezone

from google.cloud import storage
from playwright.sync_api import sync_playwright, Page

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("zozoad_report")

JST = timezone(timedelta(hours=9))
BASE = "https://to.zozo.jp/to/"
DL_TPL = (BASE + "AdReports.asp?c={c}&type={type}"
          "&SearchShopID={shop_id}&BeginDate={d}&EndDate={d}")

BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
HEADLESS = os.getenv("HEADLESS", "1") == "1"
FORCE = os.getenv("FORCE", "0") == "1"

# 4種類のレポートCSV。name=GCSファイル名。品番別は ETL 互換のため Detail.csv 据え置き。
REPORT_TYPES = [
    {"name": "daily",        "c": "DailyCSVDownLoad",      "type": "shop",      "label": "日別CSV"},
    {"name": "Detail",       "c": "GoodsInfoCSVDownLoad",  "type": "brandcode", "label": "品番別CSV"},
    {"name": "upload_goods", "c": "UploadGoodsCSVDownLoad", "type": "goodslist", "label": "アップロード品番CSV"},
    {"name": "detail_report", "c": "DetailCSVDownLoad",     "type": "brandcode", "label": "詳細CSV"},
]

ZOZOAD_SHOPS: list[tuple[str, str]] = [
    ("MONO-MART", "1787"), ("EMMA CLOTHES", "2031"), ("Chaco closet", "2258"),
    ("ADRER", "2395"), ("anown", "2524"), ("Anchor Smith", "2525"), ("BONLECILL", "2710"),
]


def _get_fetch_date() -> str:
    lag = int(os.getenv("ZOZOAD_LAG_DAYS", "1"))
    env = os.getenv("TARGET_DATE")
    if env:
        try:
            base = datetime.fromisoformat(env)
        except Exception:
            return env
    else:
        base = datetime.now(JST) - timedelta(days=1)
    return (base - timedelta(days=lag)).strftime("%Y-%m-%d")


def _run_date() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def _looks_like_csv(data: bytes) -> bool:
    if len(data) < 50:
        return False
    head = data[:300].lower()
    if b"<html" in head or b"<!doctype" in head:
        return False
    try:
        sample = data[:600].decode("cp932", errors="replace")
    except Exception:
        return False
    return any(h in sample for h in ("ショップ", "ROAS", "imp", "click", "日付", "品番"))


def _has_data_rows(data: bytes) -> bool:
    """ヘッダのみ(=未反映)でなく、実データ行があるか。"""
    try:
        lines = [l for l in data.decode("cp932", "replace").splitlines() if l.strip()]
    except Exception:
        return False
    return len(lines) >= 2


def _login(page: Page) -> None:
    page.goto(BASE, wait_until="domcontentloaded", timeout=30_000)
    if page.locator('input[name="LoginName"]').count() > 0:
        page.fill('input[name="LoginName"]', os.environ["ZOZO_LOGIN_ID"])
        page.fill('input[name="Password"]', os.environ["ZOZO_LOGIN_PASSWORD"])
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            page.get_by_role("button", name="ログイン").first.click()
    logger.info("Login OK: %s", page.url)


def _establish_search(page: Page, d_slash: str) -> None:
    page.goto(BASE + "AdReports.asp?c=Init", wait_until="domcontentloaded", timeout=45_000)
    time.sleep(1)
    page.evaluate(r"""(d) => {
      const f = document.forms['form'] || document.querySelector('form[action="AdReports.asp"]');
      if (!f) return;
      for (const n of ['TermFrom','TermTo']) { const i=f.querySelector(`input[name="${n}"]`); if(i) i.value=d; }
      const cb=f.querySelector('input[name="DailyFlag"]'); if(cb) cb.checked=true;
      const sel=f.querySelector('select[name="ShopID"]'); if(sel) sel.value='-1';
    }""", d_slash)
    with page.expect_navigation(wait_until="domcontentloaded", timeout=60_000):
        page.locator('button[name="search"][value="search"]').first.click()
    time.sleep(2)


def _fetch_one_type(context, page, rt: dict, fetch_date: str) -> bool:
    """1種類を全ショップ取得→統合→GCS保存。実データ行があれば True。
    種類ごとに検索を貼り直す（28連続GETで検索コンテキストがリセットされるため）。"""
    _establish_search(page, fetch_date.replace("-", "/"))
    first_header: bytes | None = None
    parts: list[bytes] = []
    summary: list[str] = []
    for label, shop_id in ZOZOAD_SHOPS:
        url = DL_TPL.format(c=rt["c"], type=rt["type"], shop_id=shop_id, d=fetch_date)
        try:
            r = context.request.get(url, timeout=120_000, headers={"referer": BASE + "AdReports.asp"})
            if r.status != 200:
                logger.warning("  [%s] %s HTTP %d", rt["label"], label, r.status)
                continue
            data = r.body()
            if not _looks_like_csv(data):
                logger.warning("  [%s] %s: not CSV (%dB)", rt["label"], label, len(data))
                continue
            summary.append(f"{label}={len(data):,}B")
            if first_header is None:
                first_header = data
                parts.append(data)
            else:
                idx = data.find(b"\r\n")
                parts.append(data[idx + 2:] if idx >= 0 else data)
        except Exception as exc:
            logger.warning("  [%s] %s failed: %s", rt["label"], label, exc)
    if not parts:
        logger.warning("  [%s] 全ショップ取得失敗", rt["label"])
        return False
    merged = b"".join(parts)
    gcs_key = f"uploads/zozo/zozoad/{fetch_date}/{rt['name']}.csv"
    storage.Client().bucket(BUCKET).blob(gcs_key).upload_from_string(
        merged, content_type="text/csv; charset=shift_jis")
    has_rows = _has_data_rows(merged)
    logger.info("  [%s] %d/%d shops, %s bytes, データ行=%s → gs://%s/%s",
                rt["label"], len(parts), len(ZOZOAD_SHOPS), f"{len(merged):,}",
                has_rows, BUCKET, gcs_key)
    return has_rows


def main() -> int:
    fetch_date = _get_fetch_date()
    run_date = _run_date()
    bucket = storage.Client().bucket(BUCKET)
    marker = bucket.blob(f"uploads/zozo/zozoad/_success/{run_date}.done")

    # 既に今日成功していればスキップ（リトライ運用の要）
    if not FORCE and marker.exists():
        logger.info("本日(%s)は既に取得成功済み → スキップ (FORCE=1 で強制再取得)", run_date)
        return 0

    logger.info("ZOZOAD 4種類CSV fetch start (fetch_date=%s, run_date=%s)", fetch_date, run_date)
    if not os.getenv("ZOZO_LOGIN_ID") or not os.getenv("ZOZO_BASIC_USER"):
        logger.error("FATAL: ZOZO credentials missing"); return 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            context = browser.new_context(
                locale="ja-JP", viewport={"width": 1440, "height": 1100},
                http_credentials={"username": os.environ["ZOZO_BASIC_USER"],
                                  "password": os.environ["ZOZO_BASIC_PASSWORD"]},
                accept_downloads=True)
            page = context.new_page()
            _login(page)

            results = {}
            for rt in REPORT_TYPES:
                results[rt["name"]] = _fetch_one_type(context, page, rt, fetch_date)

            got_any_data = any(results.values())
            all_present = all(results.values())  # 4種類とも実データ行あり

            if all_present:
                marker.upload_from_string(
                    f"ok {datetime.now(JST).isoformat()} types={list(results)}",
                    content_type="text/plain")
                logger.info("✓ 4種類すべて実データ取得 → 成功マーカー記録。リトライ終了。")
                return 0
            if got_any_data:
                logger.warning("一部のみ実データ (%s)。データ未反映の可能性 → 次のリトライ時刻で再取得。", results)
                return 4   # 部分的 → 未成功扱い（次のスケジュールで再試行）
            logger.warning("全種類でデータ未反映 (ヘッダのみ等) → 次のリトライ時刻で再取得。")
            return 3
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
