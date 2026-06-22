"""
GCS → BigQuery 取り込み: クライアント提供の過去 受注・発送 (2024-07〜2025-08)。

backfill_drive_to_gcs.py で GCS へ移送済みの:
  uploads/zozo/orders/{YYYY-MM-DD}/*.csv     (日別)
  uploads/zozo/shipped/{YYYY-MM-01}/*.csv    (月次1ファイル)
を parse_orders で解析し analytics_layer.sales_daily へ upsert する。

upsert_sales_daily は rows 内の実 (sale_date, source_file) ペアで DELETE するため
日別・月次どちらの粒度でも冪等。再実行で重複しない。

再開可能: BigQuery に既に入っている sale_date はスキップ。

使い方:
  python backfill_ingest_sales.py --start 2024-07-01 --end 2025-08-31
  python backfill_ingest_sales.py --start 2024-07-01 --end 2024-07-31  # 1ヶ月テスト
  python backfill_ingest_sales.py --only shipped

ENV: GOOGLE_APPLICATION_CREDENTIALS, GCS_RAW_BUCKET
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from google.cloud import storage, bigquery
from extractors.zozo_csv_extractor import ZOZOCsvExtractor
from loaders.bigquery_loader import BigQueryLoader

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_ingest_sales")

PROJECT = "mono-back-office-system"
BUCKET = os.getenv("GCS_RAW_BUCKET", "mono-back-office-system-raw-data")


def _existing_dates(bq_client: bigquery.Client, source_file: str,
                    lo: str, hi: str) -> set[str]:
    """既に sales_daily に入っている sale_date 集合 (再開用)。"""
    q = f"""
    SELECT DISTINCT FORMAT_DATE('%Y-%m-%d', sale_date) AS d
    FROM `analytics_layer.sales_daily`
    WHERE source_file = @sf AND sale_date BETWEEN @lo AND @hi
    """
    job = bq_client.query(q, job_config=bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("sf", "STRING", source_file),
            bigquery.ScalarQueryParameter("lo", "DATE", lo),
            bigquery.ScalarQueryParameter("hi", "DATE", hi),
        ]))
    return {r.d for r in job.result()}


def _day_folders(gcs: storage.Client, sub: str, lo: date, hi: date) -> dict[str, list]:
    """uploads/zozo/{sub}/{date}/ 配下の blob を date → [blob] でまとめる。"""
    out: dict[str, list] = {}
    for blob in gcs.list_blobs(BUCKET, prefix=f"uploads/zozo/{sub}/"):
        parts = blob.name.split("/")
        if len(parts) < 5 or not parts[3]:
            continue
        d = parts[3]
        if len(d) != 10:
            continue
        try:
            dd = date.fromisoformat(d)
        except ValueError:
            continue
        if lo <= dd <= hi:
            out.setdefault(d, []).append(blob)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-07-01")
    ap.add_argument("--end",   default="2025-08-31")
    ap.add_argument("--only", choices=["orders", "shipped"], default=None)
    args = ap.parse_args()
    lo, hi = args.start, args.end

    ext = ZOZOCsvExtractor()
    bq = BigQueryLoader(project=PROJECT)
    bqc = bigquery.Client(project=PROJECT)
    gcs = storage.Client()

    sources = [s for s in ("orders", "shipped")
               if args.only is None or args.only == s]
    logger.info("Ingest sales backfill %s〜%s sources=%s", lo, hi, sources)

    total = 0
    for source in sources:
        sub = source  # orders / shipped
        is_shipped = (source == "shipped")
        existing = _existing_dates(bqc, source, lo, hi)
        logger.info("[%s] 既にBQに存在する日数: %d", source, len(existing))
        folders = _day_folders(gcs, sub, date.fromisoformat(lo), date.fromisoformat(hi))
        logger.info("[%s] GCS フォルダ数: %d", source, len(folders))

        # 月単位にまとめて 1 ロードジョブで取り込む (ジョブ固定オーバヘッド削減)
        by_month: dict[str, list[str]] = {}
        for d in sorted(folders):
            by_month.setdefault(d[:7], []).append(d)

        for ym, day_keys in sorted(by_month.items()):
            # その月の全日付が既にBQにあれば月ごとスキップ
            if all(d in existing for d in day_keys):
                logger.info("  [%s %s] SKIP (取込済み %d日)", source, ym, len(day_keys))
                continue
            # 月内の日別ファイルを並列でダウンロード＋パース (I/O重畳で高速化)
            jobs = [(d, blob) for d in day_keys for blob in folders[d]]

            def _parse(job):
                d, blob = job
                try:
                    return ext.parse_orders(blob.download_as_bytes(), d,
                                            is_shipped=is_shipped)
                except Exception as exc:
                    logger.error("  parse失敗 %s: %s", blob.name, exc)
                    return []

            rows = []
            with ThreadPoolExecutor(max_workers=8) as ex:
                for part in ex.map(_parse, jobs):
                    rows.extend(part)
            if not rows:
                continue
            try:
                # 月初日付を渡すが、upsert は rows 内の実 (sale_date, source) で
                # DELETE するため月内全日付が正しく置換される。
                bq.upsert_sales_daily(rows, day_keys[0])
                total += len(rows)
                ndates = len({r["sale_date"] for r in rows})
                logger.info("  [%s %s] ✓ %d rows / %d dates (1 load job)",
                            source, ym, len(rows), ndates)
            except Exception as exc:
                logger.error("  [%s %s] ✗ upsert失敗: %s", source, ym, str(exc)[:160])

    logger.info("=== sales ingest 完了: 合計 %d rows ===", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
