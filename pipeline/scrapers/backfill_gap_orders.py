"""
ZOZO BO 受注・発送 過去データ バックフィル (月次レンジ) — GCS移送のみ。

背景:
  クライアント提供の過去データは 2024/7〜2025/8 まで (Drive→GCS済み)。
  2025/9〜2026/5/24 の欠落は ZOZO BO の「直近1年」ウィンドウ内なので
  ZOZO BO から直接取得できる。
  ただし旧 backfill_orders.py のスクレイプはログインに失敗し HTML を掴むため
  使用しない。本スクリプトは「動いている」日次スクレイパー zozo_scraper の
  ログイン(_login)・認証付きPOST(_dl_form_post)・CSV検証(_looks_like_csv)を
  そのまま再利用し、月次レンジ (TermFrom=月初, TermTo=月末) で取得する。

GCS 出力:
  uploads/zozo/orders/{YYYY-MM-01}/orders_{YYYYMM}.csv    (1ファイル=1ヶ月)
  uploads/zozo/shipped/{YYYY-MM-01}/shipped_{YYYYMM}.csv
  ※ 月次1ファイルだが、取り込み(parse_orders)は行ごとに 注文日/出荷日 から
     sale_date を決めるため、日別パーティションに正しく振り分く。

使い方:
  python backfill_gap_orders.py --start 2025-09 --end 2026-05
  python backfill_gap_orders.py --start 2025-09 --end 2025-09   # 1ヶ月テスト

ENV: ZOZO_BASIC_USER/PASSWORD, ZOZO_LOGIN_ID/PASSWORD,
     GCS_RAW_BUCKET, GOOGLE_APPLICATION_CREDENTIALS, HEADLESS(=1)
"""
from __future__ import annotations

import argparse
import calendar
import dataclasses
import logging
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright
from google.cloud import storage
from zozo_scraper import ZOZOScraper, SOURCES  # 動作実績のあるスクレイパー

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_gap")

BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")
SKIP_EXISTING = os.getenv("SKIP_EXISTING", "1") == "1"

# zozo_scraper.SOURCES から orders/shipped のテンプレを取得
_SRC = {s.name: s for s in SOURCES}


def _days(start_iso: str, end_iso: str) -> list[date]:
    from datetime import timedelta
    s = date.fromisoformat(start_iso)
    e = date.fromisoformat(end_iso)
    out = []
    d = s
    while d <= e:
        out.append(d)
        d += timedelta(days=1)
    return out


def _enc(d: date) -> str:
    return d.strftime("%Y%%2F%m%%2F%d")  # YYYY%2FMM%2FDD


def _daily_src(name: str, day: date):
    """orders/shipped の SourceConfig をコピーし、単日({D})の日付を焼き込む。
    日次パイプラインで実績のある単日POSTをそのまま使う(レンジ不可のため)。"""
    base = _SRC[name]
    baked = base.post_template.replace("{D}", _enc(day))
    fn = f"{name}.csv"
    return dataclasses.replace(base, post_template=baked, filename_default=fn)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="開始日 YYYY-MM-DD")
    ap.add_argument("--end",   required=True, help="終了日 YYYY-MM-DD")
    ap.add_argument("--only", choices=["orders", "shipped"], default=None)
    args = ap.parse_args()

    for k in ("ZOZO_BASIC_USER", "ZOZO_BASIC_PASSWORD",
              "ZOZO_LOGIN_ID", "ZOZO_LOGIN_PASSWORD"):
        if not os.getenv(k):
            logger.error("FATAL: %s が未設定", k); return 2

    sources = [s for s in ("orders", "shipped")
               if args.only is None or args.only == s]
    days = _days(args.start, args.end)
    logger.info("Gap backfill: %d 日 × %s (%s〜%s)",
                len(days), sources, args.start, args.end)

    gcs = storage.Client()
    scraper = ZOZOScraper(
        basic_user=os.environ["ZOZO_BASIC_USER"],
        basic_pw=os.environ["ZOZO_BASIC_PASSWORD"],
        login_id=os.environ["ZOZO_LOGIN_ID"],
        password=os.environ["ZOZO_LOGIN_PASSWORD"],
        headless=os.getenv("HEADLESS", "1") == "1",
    )

    ok = fail = skip = 0
    with tempfile.TemporaryDirectory() as tmp:
        dl_dir = Path(tmp)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=scraper.headless)
            try:
                context = scraper._new_context(browser)
                page = context.new_page()
                scraper._login(page)

                for day in days:
                    folder = day.strftime("%Y-%m-%d")
                    scraper.target_date = folder   # _download_source が使う日付
                    for name in sources:
                        key = f"uploads/zozo/{name}/{folder}/{name}.csv"
                        if SKIP_EXISTING and gcs.bucket(BUCKET).blob(key).exists():
                            skip += 1; continue
                        # 日次パイプラインと同じ完全フロー(ページ遷移→カスケード
                        # ダウンロード→CSV検証→GCSアップロード)をそのまま再利用。
                        result = scraper._download_source(context, page, _SRC[name], dl_dir)
                        if result.get("status") == "ok":
                            ok += 1
                            logger.info("  [%s %s] ✓ %s", name, folder,
                                        result.get("size_bytes"))
                        else:
                            fail += 1
                            logger.error("  [%s %s] ✗ %s", name, folder,
                                         str(result.get("error"))[:140])
            finally:
                browser.close()

    logger.info("=== gap backfill 完了: ok=%d skip=%d fail=%d ===", ok, skip, fail)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
