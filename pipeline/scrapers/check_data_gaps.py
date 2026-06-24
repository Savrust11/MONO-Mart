"""データ欠損の自動検知 (日次取込の取りこぼし監視)。

背景 (2026-06):
  6/21・6/22 の受注取込が 0 行のまま success として記録され、失敗アラートが
  飛ばずに顧客指摘で初めて発覚した。既存の監視は「ステップ失敗」しか検知せず、
  「成功したが 0 行 / 異常に少ない」ケースを取りこぼす。本スクリプトはその穴を埋める。

  さらに 6/24 の調査で、別系統の取りこぼしも判明した:
    ・商品別実績 (performance: UU/CVR/お気に率の元データ) が 6/22・6/23 で欠損。
    ・performance は店舗別に取得するため、特定の店舗 (例: MONO-MART) だけが
      抜ける「一部店舗欠損」が 5/11..5/24 で発生 (7店舗中5店舗のみ)。
  受注(orders)だけを見る監視ではこれらを検知できないため、本版で
  performance の日次欠損と「重要店舗の欠損」も併せて監視する。

やること:
  1. analytics_layer.sales_daily を sale_date 別・source_file 別に集計。
  2. 直近 N 日 (既定 35) の各日について、source ごとに:
       - 行が無い / 0 行          -> MISSING (重大)
       - 0 < 行 < しきい値        -> LOW     (警告)  ※平常日の中央値 * frac と下限の大きい方
     対象 source: orders(販売数/金額) と performance(UU/CVR/お気に率)。
  3. performance がある日について、基準店舗集合に対して重要店舗
     (既定: MONO-MART) が欠けていれば SHOP_GAP として検知。
  4. 異常があれば:
       - 監視テーブル monitoring.pipeline_runs に step='data_gap_check' で記録
         (status=failed)。-> 既存ダッシュボード/ステータスAPIに表示される。
       - Slack に通知 (SLACK_WEBHOOK_URL があれば)。
       - 復旧コマンド (run_recover_dates.ps1 -Dates ...) を出力。
         orders 欠損は既定ソース、performance/店舗欠損は -Sources "performance"。
  5. 異常があれば exit 1、無ければ exit 0。

使い方:
  python check_data_gaps.py                  # 直近35日を監視
  python check_data_gaps.py --days 60
  python check_data_gaps.py --start 2026-05-01 --end 2026-06-22
  python check_data_gaps.py --min-rows 500 --frac 0.2          # orders しきい値調整
  python check_data_gaps.py --perf-min-rows 200               # performance しきい値
  python check_data_gaps.py --critical-shops "MONO-MART,anown" # 重要店舗を指定
  python check_data_gaps.py --skip-performance                # orders のみ (旧挙動)

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
DEFAULT_DAYS = 35            # 監視する直近日数
DEFAULT_MIN_ROWS = 500      # orders: この行数を下回る日は疑わしい(絶対下限)
DEFAULT_FRAC = 0.2          # 平常日の中央値に対する比率しきい値
DEFAULT_PERF_MIN_ROWS = 200  # performance: 絶対下限 (店舗×品番なので orders より小)
DEFAULT_CRITICAL_SHOPS = "MONO-MART"  # この店舗が欠けたら SHOP_GAP (主力店舗)


def _daily_counts(bq: bigquery.Client, start: date, end: date,
                  source_file: str) -> dict[str, int]:
    """start..end の各 sale_date の指定 source 行数を返す (存在しない日はキー無し)。"""
    # NB: `rows` is a reserved keyword in BigQuery -> alias must be n_rows.
    q = f"""
      SELECT CAST(sale_date AS STRING) AS d, COUNT(*) AS n_rows
      FROM `{GCP_PROJECT_ID}.{BQ_DATASET_ANALYTICS}.sales_daily`
      WHERE source_file = @sf
        AND sale_date BETWEEN DATE(@s) AND DATE(@e)
      GROUP BY d
    """
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("sf", "STRING", source_file),
        bigquery.ScalarQueryParameter("s", "STRING", start.isoformat()),
        bigquery.ScalarQueryParameter("e", "STRING", end.isoformat()),
    ])
    return {r.d: r.n_rows for r in bq.query(q, job_config=cfg)}


def _perf_shop_coverage(bq: bigquery.Client, start: date,
                        end: date) -> dict[str, set[str]]:
    """performance について、各 sale_date に存在する shop_name 集合を返す。"""
    q = f"""
      SELECT CAST(sale_date AS STRING) AS d, shop_name
      FROM `{GCP_PROJECT_ID}.{BQ_DATASET_ANALYTICS}.sales_daily`
      WHERE source_file = 'performance'
        AND shop_name IS NOT NULL AND shop_name != ''
        AND sale_date BETWEEN DATE(@s) AND DATE(@e)
      GROUP BY d, shop_name
    """
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("s", "STRING", start.isoformat()),
        bigquery.ScalarQueryParameter("e", "STRING", end.isoformat()),
    ])
    cov: dict[str, set[str]] = {}
    for r in bq.query(q, job_config=cfg):
        cov.setdefault(r.d, set()).add(r.shop_name)
    return cov


def _classify(counts: dict[str, int], start: date, end: date,
              min_rows: int, frac: float) -> tuple[list[str], list[tuple[str, int]], int, int]:
    """日次行数から MISSING / LOW を判定。baseline と threshold も返す。"""
    nonzero = [v for v in counts.values() if v > 0]
    median = int(statistics.median(nonzero)) if nonzero else 0
    low_threshold = max(min_rows, int(median * frac))
    missing: list[str] = []
    low: list[tuple[str, int]] = []
    d = start
    while d <= end:
        ds = d.isoformat()
        n = counts.get(ds, 0)
        if n == 0:
            missing.append(ds)
        elif n < low_threshold:
            low.append((ds, n))
        d += timedelta(days=1)
    return missing, low, median, low_threshold


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


def _recover_cmd(dates: list[str], sources: str | None = None) -> str:
    fix_list = ",".join(f'"{ds}"' for ds in dates)
    cmd = f"powershell -ExecutionPolicy Bypass -File run_recover_dates.ps1 -Dates {fix_list}"
    if sources:
        cmd += f' -Sources "{sources}"'
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (指定時 --days を無視)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (既定: 昨日 JST)")
    ap.add_argument("--min-rows", type=int, default=DEFAULT_MIN_ROWS,
                    help="orders の絶対下限")
    ap.add_argument("--frac", type=float, default=DEFAULT_FRAC)
    ap.add_argument("--perf-min-rows", type=int, default=DEFAULT_PERF_MIN_ROWS,
                    help="performance の絶対下限")
    ap.add_argument("--critical-shops", default=DEFAULT_CRITICAL_SHOPS,
                    help="この店舗が performance から欠けたら SHOP_GAP (カンマ区切り)")
    ap.add_argument("--skip-performance", action="store_true",
                    help="orders のみ監視 (performance/店舗チェックを行わない)")
    ap.add_argument("--emit-dates", default=None,
                    help="write the missing/low ORDERS dates (one per line) to this file "
                         "so a backfill wrapper can consume them")
    ap.add_argument("--emit-perf-dates", default=None,
                    help="write the performance/shop-gap dates (one per line) to this file")
    args = ap.parse_args()

    today_jst = datetime.now(JST).date()
    end = date.fromisoformat(args.end) if args.end else (today_jst - timedelta(days=1))
    start = date.fromisoformat(args.start) if args.start else (end - timedelta(days=args.days - 1))
    checked_days = (end - start).days + 1

    bq = bigquery.Client(project=GCP_PROJECT_ID)

    # ── (1) orders 日次欠損 ────────────────────────────────────────────────
    ord_counts = _daily_counts(bq, start, end, "orders")
    ord_missing, ord_low, ord_median, ord_thr = _classify(
        ord_counts, start, end, args.min_rows, args.frac)

    logger.info("=== data gap check: %s .. %s (%d days) ===", start, end, checked_days)
    logger.info("[orders]      median(nonzero)=%d  low_threshold=%d  missing=%d low=%d",
                ord_median, ord_thr, len(ord_missing), len(ord_low))

    # ── (2) performance 日次欠損 + (3) 重要店舗欠損 ────────────────────────
    perf_missing: list[str] = []
    perf_low: list[tuple[str, int]] = []
    shop_gaps: dict[str, set[str]] = {}   # date -> 欠けている重要店舗
    perf_median = perf_thr = 0
    ref_shops: set[str] = set()
    critical = {s.strip() for s in args.critical_shops.split(",") if s.strip()}

    if not args.skip_performance:
        perf_counts = _daily_counts(bq, start, end, "performance")
        perf_missing, perf_low, perf_median, perf_thr = _classify(
            perf_counts, start, end, args.perf_min_rows, args.frac)
        # performance はある日 (5/05〜) のみ対象。それ以前は元々存在しないので
        # MISSING から除外する (取込開始日より前を誤検知しない)。
        if perf_counts:
            perf_first = min(perf_counts)
            perf_missing = [d for d in perf_missing if d >= perf_first]
            perf_low = [(d, n) for d, n in perf_low if d >= perf_first]

        # 店舗カバレッジ: 基準集合 = 窓内で最も店舗数が多い日の集合。
        cov = _perf_shop_coverage(bq, start, end)
        for s in cov.values():
            if len(s) > len(ref_shops):
                ref_shops = set(s)
        # performance がある日について、重要店舗の欠損を判定。
        for ds, shops in cov.items():
            missing_shops = critical - shops
            if missing_shops:
                shop_gaps[ds] = missing_shops
            other_missing = (ref_shops - shops) - critical
            if other_missing:
                logger.info("  (info) %s : 非重要店舗欠損 %s",
                            ds, sorted(other_missing))

        logger.info("[performance] median(nonzero)=%d  low_threshold=%d  missing=%d low=%d",
                    perf_median, perf_thr, len(perf_missing), len(perf_low))
        logger.info("[shops] reference=%s  critical=%s  shop_gap_days=%d",
                    sorted(ref_shops), sorted(critical), len(shop_gaps))

    # ── 集計・判定 ────────────────────────────────────────────────────────
    any_gap = bool(ord_missing or ord_low or perf_missing or perf_low or shop_gaps)

    if not any_gap:
        logger.info("OK: no gaps detected (orders + performance + shops).")
        _record_monitoring(bq, end.isoformat(), "success", len(ord_counts), None)
        if args.emit_dates:
            open(args.emit_dates, "w").close()
        if args.emit_perf_dates:
            open(args.emit_perf_dates, "w").close()
        return 0

    # 詳細ログ
    for ds in ord_missing:
        logger.info("  ORDERS  MISSING  %s : 0 rows", ds)
    for ds, n in ord_low:
        logger.info("  ORDERS  LOW      %s : %d rows (< %d)", ds, n, ord_thr)
    for ds in perf_missing:
        logger.info("  PERF    MISSING  %s : 0 rows", ds)
    for ds, n in perf_low:
        logger.info("  PERF    LOW      %s : %d rows (< %d)", ds, n, perf_thr)
    for ds in sorted(shop_gaps):
        logger.info("  PERF    SHOP_GAP %s : 欠損店舗 %s", ds, sorted(shop_gaps[ds]))

    # 復旧対象日 (orders 系 / performance 系) を分けて算出
    ord_bad = sorted(set(ord_missing) | {d for d, _ in ord_low})
    perf_bad = sorted(set(perf_missing) | {d for d, _ in perf_low} | set(shop_gaps))

    if args.emit_dates:
        with open(args.emit_dates, "w") as fh:
            fh.write("\n".join(ord_bad) + ("\n" if ord_bad else ""))
    if args.emit_perf_dates:
        with open(args.emit_perf_dates, "w") as fh:
            fh.write("\n".join(perf_bad) + ("\n" if perf_bad else ""))

    logger.info("--- to fix, run on the production server: ---")
    if ord_bad:
        logger.info("  [orders]      %s", _recover_cmd(ord_bad))
    if perf_bad:
        logger.info("  [performance] %s", _recover_cmd(perf_bad, sources="performance"))

    # 監視テーブル記録 + Slack
    msg = (f"data gaps {start}..{end}: "
           f"ORDERS missing={ord_missing} low={[d for d, _ in ord_low]}; "
           f"PERF missing={perf_missing} low={[d for d, _ in perf_low]} "
           f"shop_gap={ {d: sorted(v) for d, v in shop_gaps.items()} }")
    _record_monitoring(bq, end.isoformat(), "failed", len(ord_counts), msg)

    slack_lines = [f":rotating_light: *Data gap detected* [{start}..{end}]"]
    if ord_missing or ord_low:
        slack_lines.append(f"*ORDERS* missing(0行): {ord_missing or 'none'} / "
                           f"low(<{ord_thr}): {[d for d, _ in ord_low] or 'none'}")
    if perf_missing or perf_low:
        slack_lines.append(f"*PERFORMANCE* missing(0行): {perf_missing or 'none'} / "
                           f"low(<{perf_thr}): {[d for d, _ in perf_low] or 'none'}")
    if shop_gaps:
        slack_lines.append(f"*SHOP GAP* (重要店舗欠損): "
                           f"{ {d: sorted(v) for d, v in shop_gaps.items()} }")
    if ord_bad:
        slack_lines.append(f"*Fix orders:* `{_recover_cmd(ord_bad)}`")
    if perf_bad:
        slack_lines.append(f"*Fix perf:* `{_recover_cmd(perf_bad, sources='performance')}`")
    _slack("\n".join(slack_lines))
    return 1


if __name__ == "__main__":
    sys.exit(main())
