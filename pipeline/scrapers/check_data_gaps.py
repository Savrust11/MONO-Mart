"""データ欠損の自動検知 (orders 日次取込の取りこぼし監視)。

背景 (2026-06):
  6/21・6/22 の受注取込が 0 行のまま success として記録され、失敗アラートが
  飛ばずに顧客指摘で初めて発覚した。既存の監視は「ステップ失敗」しか検知せず、
  「成功したが 0 行 / 異常に少ない」ケースを取りこぼす。本スクリプトはその穴を埋める。

やること:
  1. analytics_layer.sales_daily (source_file='orders') を sale_date 別に集計。
  2. 直近 N 日 (既定 35) の各日について:
       - 行が無い / 0 行          -> MISSING (重大)
       - 0 < 行 < しきい値        -> LOW     (警告)  ※平常日の中央値 * frac と下限の大きい方
  3. 異常があれば:
       - 監視テーブル monitoring.pipeline_runs に step='data_gap_check' で記録
         (status=failed)。-> 既存ダッシュボード/ステータスAPIに表示される。
       - Slack に通知 (SLACK_WEBHOOK_URL があれば)。
       - 復旧コマンド (run_recover_dates.ps1 -Dates ...) を出力。
  4. 異常があれば exit 1、無ければ exit 0。

使い方:
  python check_data_gaps.py                  # 直近35日を監視
  python check_data_gaps.py --days 60
  python check_data_gaps.py --start 2026-05-01 --end 2026-06-22
  python check_data_gaps.py --min-rows 500 --frac 0.2   # しきい値調整

ENV: GCP_PROJECT_ID, GOOGLE_APPLICATION_CREDENTIALS, SLACK_WEBHOOK_URL(任意)
"""
from __future__ import annotations

import argparse
import logging
import os
import statistics
import sys
import uuid
from datetime import datetime, date, timedelta, timezone

# pipeline/ をパスに追加して config を import 可能にする (cwd 非依存)。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from google.cloud import bigquery

from config import (
    GCP_PROJECT_ID,
    BQ_DATASET_ANALYTICS,
    BQ_DATASET_MONITORING,
    SLACK_WEBHOOK_URL,
    JST,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("check_data_gaps")

# しきい値の既定値
DEFAULT_DAYS = 35       # 監視する直近日数
DEFAULT_MIN_ROWS = 500  # この行数を下回る日は疑わしい(絶対下限)
DEFAULT_FRAC = 0.2      # 平常日の中央値に対する比率しきい値


def _daily_order_counts(bq: bigquery.Client, start: date, end: date) -> dict[str, int]:
    """start..end の各 sale_date の orders 行数を返す (存在しない日はキー無し)。"""
    # NB: `rows` is a reserved keyword in BigQuery -> alias must be n_rows.
    q = f"""
      SELECT CAST(sale_date AS STRING) AS d, COUNT(*) AS n_rows
      FROM `{GCP_PROJECT_ID}.{BQ_DATASET_ANALYTICS}.sales_daily`
      WHERE source_file = 'orders'
        AND sale_date BETWEEN DATE(@s) AND DATE(@e)
      GROUP BY d
    """
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("s", "STRING", start.isoformat()),
        bigquery.ScalarQueryParameter("e", "STRING", end.isoformat()),
    ])
    return {r.d: r.n_rows for r in bq.query(q, job_config=cfg)}


def _record_monitoring(bq: bigquery.Client, run_date: str, status: str, rows: int, msg: str | None) -> None:
    """既存 monitoring.pipeline_runs に1行記録 (ダッシュボードに反映される)。"""
    table = f"{GCP_PROJECT_ID}.{BQ_DATASET_MONITORING}.pipeline_runs"
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "run_id": str(uuid.uuid4()),
        "run_date": run_date,
        "step": "data_gap_check",
        "status": status,                 # success | failed
        "rows_processed": rows,
        "duration_ms": 0,
        "started_at": now,
        "finished_at": now,
        "error_message": msg,
    }
    try:
        errors = bq.insert_rows_json(table, [row])
        if errors:
            logger.warning("monitoring write returned: %s", errors)
    except Exception as exc:  # 監視書き込み失敗は致命的にしない
        logger.warning("monitoring write error (non-fatal): %s", exc)


def _slack(text: str) -> None:
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=5)
    except Exception as exc:
        logger.warning("slack alert failed (non-fatal): %s", exc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (指定時 --days を無視)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (既定: 昨日 JST)")
    ap.add_argument("--min-rows", type=int, default=DEFAULT_MIN_ROWS)
    ap.add_argument("--frac", type=float, default=DEFAULT_FRAC)
    ap.add_argument("--emit-dates", default=None,
                    help="write the missing/low dates (one per line) to this file "
                         "so a backfill wrapper can consume them")
    args = ap.parse_args()

    today_jst = datetime.now(JST).date()
    end = date.fromisoformat(args.end) if args.end else (today_jst - timedelta(days=1))
    start = date.fromisoformat(args.start) if args.start else (end - timedelta(days=args.days - 1))

    bq = bigquery.Client(project=GCP_PROJECT_ID)
    counts = _daily_order_counts(bq, start, end)

    # 平常日の基準 = 0より大きい日の中央値
    nonzero = [v for v in counts.values() if v > 0]
    median = int(statistics.median(nonzero)) if nonzero else 0
    low_threshold = max(args.min_rows, int(median * args.frac))

    missing: list[str] = []   # 0 行 / 存在しない
    low: list[tuple[str, int]] = []  # 少なすぎる

    d = start
    while d <= end:
        ds = d.isoformat()
        rows = counts.get(ds, 0)
        if rows == 0:
            missing.append(ds)
        elif rows < low_threshold:
            low.append((ds, rows))
        d += timedelta(days=1)

    # レポート出力
    logger.info("=== data gap check: orders %s .. %s ===", start, end)
    logger.info("baseline median(nonzero)=%d  low_threshold=%d (min_rows=%d frac=%.2f)",
                median, low_threshold, args.min_rows, args.frac)
    logger.info("checked_days=%d  missing=%d  low=%d", (end - start).days + 1, len(missing), len(low))

    if not missing and not low:
        logger.info("OK: no gaps detected.")
        _record_monitoring(bq, end.isoformat(), "success", len(counts), None)
        if args.emit_dates:
            open(args.emit_dates, "w").close()  # empty -> wrapper uploads nothing
        return 0

    for ds in missing:
        logger.info("  MISSING  %s : 0 rows", ds)
    for ds, r in low:
        logger.info("  LOW      %s : %d rows (< %d)", ds, r, low_threshold)

    bad_dates = sorted(missing + [ds for ds, _ in low])
    if args.emit_dates:
        with open(args.emit_dates, "w") as fh:
            fh.write("\n".join(bad_dates) + "\n")
    fix_list = ",".join(f'"{ds}"' for ds in bad_dates)
    fix_cmd = f"powershell -ExecutionPolicy Bypass -File run_recover_dates.ps1 -Dates {fix_list}"
    logger.info("--- to fix, run on the production server: ---")
    logger.info("  %s", fix_cmd)

    # 監視テーブルに記録 + Slack 通知
    msg = (f"orders data gaps {start}..{end}: "
           f"MISSING={missing} LOW={[d for d, _ in low]}")
    _record_monitoring(bq, end.isoformat(), "failed", len(counts), msg)
    _slack(
        f":rotating_light: *Orders data gap detected* [{start}..{end}]\n"
        f"*MISSING (0 rows):* {missing or 'none'}\n"
        f"*LOW (< {low_threshold}):* {[d for d, _ in low] or 'none'}\n"
        f"*Fix:* `{fix_cmd}`"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
