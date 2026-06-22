"""
Smart incremental backfill with BigQuery watermark tracking.

仕様書 列F = 2024/7/1〜 の6ソースを対象とする:
  No.1  受注                  → analytics_layer.sales_daily  (source_file='orders')
  No.2  発送                  → analytics_layer.sales_daily  (source_file='shipped')
  No.8  商品別実績(新)         → analytics_layer.sales_daily  (source_file='performance')
  No.18 クーポン除外           → analytics_layer.coupon_exclusion
  No.19 検索キーワード         → analytics_layer.search_keyword_daily
  No.20 アクセス実績(新)       → analytics_layer.access_log_daily
  ※ No.14 予約管理表はライブスナップショット型のためスキップ

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ウォーターマーク方式（どうして「賢い」のか）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  実行ごとに BigQuery の MAX(日付列) を読み取る。
  fetch_from = MAX(日付) + 1日、fetch_to = 昨日 (JST)

  初回実行: BigQuery にデータなし
    → fetch_from = 2024-07-01 (仕様書最古日)
    → fetch_to   = 昨日
    → 約2年分を取得

  翌日実行: BigQuery に昨日分まで存在
    → fetch_from = 今日 (= 昨日+1) > fetch_to (昨日)
    → 「取得不要」とスキップ ← ここが核心

  翌々日以降: 昨日分のみ取得
    → 差分1日だけ処理

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ダウンロード戦略
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  No.1/2 受注・発送  : order_csv.asp へ月次 POST (1リクエスト/月)
  No.8/19/20        : zozo_scraper.py を TARGET_DATE + ONLY= で1日ずつ呼出し
                      ※初回の大量バックフィルは --max-looker-days で上限指定可
  No.18 クーポン除外 : fetch_coupon_exclusion.py を1日ずつ呼出し

Usage:
  # 通常（日次 run_daily.ps1 から呼ぶ）
  python incremental_backfill.py

  # Looker系の遡及上限を変更（デフォルト 90 日、初回は 730 で全期間）
  python incremental_backfill.py --max-looker-days 730

  # 対象ソースを絞る
  python incremental_backfill.py --only orders,shipped

  # 確認のみ（実際の取得は行わない）
  python incremental_backfill.py --dry-run
"""
from __future__ import annotations

import argparse
import calendar
import logging
import os
import subprocess
import sys
import time
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("incremental_backfill")

# ── パス ─────────────────────────────────────────────────────────────────────
_HERE      = Path(__file__).resolve().parent
_PIPELINE  = _HERE.parent
_MAIN_PY   = _PIPELINE / "main.py"
_SCRAPER   = _HERE / "zozo_scraper.py"
_COUPON_PY = _HERE / "fetch_coupon_exclusion.py"

sys.path.insert(0, str(_PIPELINE))

JST = timezone(timedelta(hours=9))

# ── 定数 ─────────────────────────────────────────────────────────────────────
BACKFILL_ORIGIN = date(2024, 7, 1)          # 仕様書 列F の最古日
_DLB = "%83_%83E%83%93%83%8D%81%5B%83h"    # "ダウンロード" URL encoded

# ── ウォーターマーク定義 ─────────────────────────────────────────────────────
# source_key → (BQテーブル, 日付列, WHERE絞り込み or None)
WATERMARK_MAP: dict[str, tuple[str, str, Optional[str]]] = {
    "orders":           ("analytics_layer.sales_daily",         "sale_date",    "source_file = 'orders'"),
    "shipped":          ("analytics_layer.sales_daily",         "sale_date",    "source_file = 'shipped'"),
    "performance":      ("analytics_layer.sales_daily",         "sale_date",    "source_file = 'performance'"),
    "coupon_exclusion": ("analytics_layer.coupon_exclusion",    "exclusion_date", None),
    "search_keyword":   ("analytics_layer.search_keyword_daily","record_date",  None),
    "access_log":       ("analytics_layer.access_log_daily",    "record_date",  None),
}

# Looker系は1日ずつ呼ぶ（遡及上限あり）
LOOKER_SOURCES = {"performance", "search_keyword", "access_log"}
# 月次POSTで一括取得できるソース
BATCH_SOURCES  = {"orders", "shipped"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BigQuery ウォーターマーク取得
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_watermark(project: str, source: str) -> date:
    """
    BigQuery から MAX(日付列) を取得して返す。
    データが1件もない場合は BACKFILL_ORIGIN の前日を返す
    （= 翌日の fetch_from が BACKFILL_ORIGIN になる）。
    """
    try:
        from google.cloud import bigquery as bq
    except ImportError:
        logger.warning("google-cloud-bigquery not installed; watermark defaults to origin")
        return BACKFILL_ORIGIN - timedelta(days=1)

    table, date_col, where = WATERMARK_MAP[source]
    where_clause = f"AND {where}" if where else ""
    sql = f"""
        SELECT MAX({date_col}) AS max_date
        FROM `{project}.{table}`
        WHERE {date_col} IS NOT NULL
          {where_clause}
    """
    client = bq.Client(project=project)
    result = list(client.query(sql).result())
    max_date = result[0].max_date if result else None

    if max_date is None:
        logger.info("[%s] BigQuery にデータなし → 2024-07-01 からフル取得", source)
        return BACKFILL_ORIGIN - timedelta(days=1)

    if isinstance(max_date, str):
        max_date = date.fromisoformat(max_date)
    elif hasattr(max_date, "date"):
        max_date = max_date.date()  # datetime → date

    logger.info("[%s] BigQuery 最新日: %s", source, max_date)
    return max_date


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 受注・発送: 月次 POST バッチ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _zozo_date_enc(d: date) -> str:
    """YYYY%2FMM%2FDD"""
    return d.strftime("%Y%%2F%m%%2F%d")


def _month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """[start, end] を月ごとに分割。"""
    months: list[tuple[date, date]] = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        m_start = max(cur, start)
        m_end   = min(date(cur.year, cur.month, last_day), end)
        months.append((m_start, m_end))
        cur = (date(cur.year, cur.month, last_day) + timedelta(days=1))
    return months


def fetch_orders_batch(
    source: str,        # "orders" or "shipped"
    start: date,
    end: date,
    bucket: str,
    project: str,
    dry_run: bool,
) -> list[str]:
    """月次 POST で受注/発送 CSV を GCS へアップロード。GCS URI リストを返す。"""
    try:
        from playwright.sync_api import sync_playwright
        from google.cloud import storage as gcs
    except ImportError as e:
        logger.error("依存ライブラリ不足: %s", e)
        return []

    ost = "order" if source == "orders" else "send"
    LOGIN_URL = "https://to.zozo.jp/to/"
    POST_URL  = "https://to.zozo.jp/to/order_csv.asp"

    uris: list[str] = []
    months = _month_ranges(start, end)
    logger.info("[%s] 月次バッチ %d件: %s 〜 %s", source, len(months), start, end)

    if dry_run:
        for m_s, m_e in months:
            logger.info("  [dry-run] %s 〜 %s", m_s, m_e)
        return []

    gcs_client = gcs.Client(project=project)
    bucket_obj = gcs_client.bucket(bucket)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=(os.environ.get("HEADLESS", "1") == "1"),
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )
        page = ctx.new_page()

        # ── 2段階ログイン ──────────────────────────────────────────────
        basic_u = os.environ.get("ZOZO_BASIC_USER", "")
        basic_p = os.environ.get("ZOZO_BASIC_PASSWORD", "")
        login_id = os.environ.get("ZOZO_LOGIN_ID", "")
        login_pw = os.environ.get("ZOZO_LOGIN_PASSWORD", "")

        auth_url = LOGIN_URL.replace("https://", f"https://{basic_u}:{basic_p}@")
        page.goto(auth_url, timeout=30_000, wait_until="domcontentloaded")
        time.sleep(2)
        for sel in ('input[name="login_id"]', 'input[name="ID"]', 'input[type="text"]'):
            if page.locator(sel).count() > 0:
                page.fill(sel, login_id); break
        for sel in ('input[name="password"]', 'input[name="PASS"]', 'input[type="password"]'):
            if page.locator(sel).count() > 0:
                page.fill(sel, login_pw); break
        for sel in ('button[type="submit"]', 'input[type="submit"]'):
            if page.locator(sel).count() > 0:
                page.click(sel); break
        time.sleep(3)
        logger.info("ログイン完了")

        # ── 月ごとにダウンロード ──────────────────────────────────────
        for m_start, m_end in months:
            body = (
                f"c=Download&ShopID=-1&SCategoryPID=0&SCategoryID=0"
                f"&ost={ost}"
                f"&TermFrom={_zozo_date_enc(m_start)}"
                f"&TermTo={_zozo_date_enc(m_end)}"
                f"&MallCheck=0&DL_BUTTON={_DLB}"
            )
            try:
                import tempfile, uuid
                tmp = Path(tempfile.gettempdir()) / f"bf_{uuid.uuid4().hex}.csv"
                with page.expect_download(timeout=120_000) as dl_info:
                    page.evaluate(
                        """async ([url, body]) => {
                            const r = await fetch(url, {
                                method:'POST',
                                headers:{'Content-Type':'application/x-www-form-urlencoded'},
                                body, credentials:'include'
                            });
                            const blob = await r.blob();
                            const a = document.createElement('a');
                            a.href = URL.createObjectURL(blob);
                            a.download = 'dl.csv';
                            document.body.appendChild(a);
                            a.click();
                        }""",
                        [POST_URL, body],
                    )
                    dl = dl_info.value
                dl.save_as(str(tmp))
                data = tmp.read_bytes()
                tmp.unlink(missing_ok=True)

                # GCS アップロード
                folder    = m_start.strftime("%Y-%m-%d")
                filename  = f"{m_start.strftime('%Y_%m_%d')}_{source}.csv"
                blob_name = f"uploads/zozo/{source}/{folder}/{filename}"
                blob = bucket_obj.blob(blob_name)
                blob.upload_from_string(data, content_type="text/csv")
                uri = f"gs://{bucket}/{blob_name}"
                uris.append(uri)
                logger.info("  ✅ %s 〜 %s → %s (%d bytes)", m_start, m_end, uri, len(data))
            except Exception as exc:
                logger.error("  ❌ %s 〜 %s: %s", m_start, m_end, exc)
            time.sleep(3)

        browser.close()
    return uris


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Looker 系 / クーポン除外: 日次呼び出し
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _zozo_scraper_only_map(source: str) -> str:
    """zozo_scraper.py の ONLY= 値を返す。"""
    return {
        "performance":   "performance",
        "search_keyword":"search_keyword",
        "access_log":    "access_log_app,access_log_pcsp",
    }[source]


def fetch_daily_source(source: str, target_date: date, dry_run: bool) -> int:
    """
    zozo_scraper.py または fetch_coupon_exclusion.py を
    TARGET_DATE=target_date, ONLY=source で呼び出す。
    戻り値: 終了コード (0=成功)
    """
    date_str = target_date.strftime("%Y-%m-%d")

    if source == "coupon_exclusion":
        script = str(_COUPON_PY)
        env_extra = {"TARGET_DATE": date_str}
    else:
        script    = str(_SCRAPER)
        env_extra = {
            "TARGET_DATE": date_str,
            "ONLY":        _zozo_scraper_only_map(source),
            "HEADLESS":    "1",
        }

    if dry_run:
        logger.info("  [dry-run] %s %s", source, date_str)
        return 0

    env = {**os.environ, **env_extra}
    result = subprocess.run(
        [sys.executable, script],
        env=env,
        cwd=str(_HERE),
    )
    return result.returncode


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ETL ingest
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_etl(target_date: date, dry_run: bool) -> int:
    date_str = target_date.strftime("%Y-%m-%d")
    if dry_run:
        logger.info("  [dry-run] ETL %s", date_str)
        return 0
    result = subprocess.run(
        [sys.executable, str(_MAIN_PY), "--csv-ingest", "--date", date_str],
        cwd=str(_PIPELINE),
    )
    return result.returncode


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# メイン
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main() -> None:
    parser = argparse.ArgumentParser(
        description="インクリメンタルバックフィル（ウォーターマーク方式）"
    )
    parser.add_argument(
        "--only",
        default="orders,shipped,performance,coupon_exclusion,search_keyword,access_log",
        help="取得するソース（カンマ区切り）",
    )
    parser.add_argument(
        "--max-looker-days", type=int, default=90,
        help=(
            "Looker系ソース（performance/search_keyword/access_log）の "
            "最大遡及日数。初回フル取得は 730 を指定。(default: 90)"
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="計画のみ表示。実際の取得・ETLは実行しない")
    args = parser.parse_args()

    project = os.environ.get("GCP_PROJECT_ID", "mono-back-office-system")
    bucket  = os.environ.get("GCS_RAW_BUCKET",  f"{project}-raw-data")
    sources = [s.strip() for s in args.only.split(",")]

    # 昨日（JST）が fetch_to の上限
    yesterday = (datetime.now(JST) - timedelta(days=1)).date()

    logger.info("═" * 60)
    logger.info("インクリメンタルバックフィル開始")
    logger.info("  プロジェクト : %s", project)
    logger.info("  バケット     : %s", bucket)
    logger.info("  対象ソース   : %s", sources)
    logger.info("  fetch_to 上限: %s (昨日 JST)", yesterday)
    logger.info("  Looker 上限  : %d 日", args.max_looker_days)
    if args.dry_run:
        logger.info("  [DRY RUN モード]")
    logger.info("═" * 60)

    summary: list[dict] = []

    for source in sources:
        if source not in WATERMARK_MAP:
            logger.warning("未知のソース '%s' をスキップ", source)
            continue

        logger.info("")
        logger.info("── %s ──────────────────────────────────────────", source)

        # ① ウォーターマーク取得
        watermark  = get_watermark(project, source)
        fetch_from = watermark + timedelta(days=1)
        fetch_to   = yesterday

        # ② Looker 系は max-looker-days で遡及上限を設ける
        if source in LOOKER_SOURCES:
            looker_limit = yesterday - timedelta(days=args.max_looker_days - 1)
            if fetch_from < looker_limit:
                logger.info(
                    "  Looker 上限(%d日)を適用: %s → %s",
                    args.max_looker_days, fetch_from, looker_limit,
                )
                fetch_from = looker_limit

        # ③ スキップ判定 ─ 最も重要なロジック
        if fetch_from > fetch_to:
            logger.info(
                "  ✅ 取得不要（BQ最新: %s = 昨日）— スキップ", watermark
            )
            summary.append({"source": source, "status": "skip",
                             "watermark": str(watermark)})
            continue

        days_to_fetch = (fetch_to - fetch_from).days + 1
        logger.info(
            "  📥 取得範囲: %s 〜 %s （%d日分）",
            fetch_from, fetch_to, days_to_fetch,
        )

        # ④ ダウンロード
        if source in BATCH_SOURCES:
            # 月次 POST バッチ（受注・発送）
            uris = fetch_orders_batch(
                source, fetch_from, fetch_to, bucket, project, args.dry_run
            )
            # ETL: 月の先頭日付ごとに run
            for m_start, _ in _month_ranges(fetch_from, fetch_to):
                rc = run_etl(m_start, args.dry_run)
                if rc != 0:
                    logger.warning("  ⚠️ ETL 終了コード %d (month=%s)", rc, m_start)
            summary.append({
                "source": source, "status": "ok",
                "fetched_from": str(fetch_from), "fetched_to": str(fetch_to),
                "months": len(_month_ranges(fetch_from, fetch_to)),
            })

        else:
            # 日次呼び出し（Looker 系 / クーポン除外）
            ok_count = fail_count = 0
            cur = fetch_from
            while cur <= fetch_to:
                rc = fetch_daily_source(source, cur, args.dry_run)
                if rc == 0:
                    ok_count += 1
                else:
                    fail_count += 1
                    logger.warning("  ⚠️ %s %s: exit=%d", source, cur, rc)
                # ETL は日次で実行（失敗してもスキップせず続行）
                run_etl(cur, args.dry_run)
                cur += timedelta(days=1)
                time.sleep(2)  # ZOZO への負荷軽減

            summary.append({
                "source": source, "status": "ok" if fail_count == 0 else "partial",
                "fetched_from": str(fetch_from), "fetched_to": str(fetch_to),
                "ok": ok_count, "fail": fail_count,
            })

    # ── サマリー表示 ─────────────────────────────────────────────
    logger.info("")
    logger.info("═" * 60)
    logger.info("実行結果サマリー")
    logger.info("%-20s %-10s %s", "ソース", "状態", "詳細")
    logger.info("─" * 60)
    for r in summary:
        if r["status"] == "skip":
            detail = f"BQ最新日={r['watermark']} → 取得不要"
        elif "months" in r:
            detail = f"{r['fetched_from']}〜{r['fetched_to']} ({r['months']}ヶ月)"
        else:
            detail = (f"{r['fetched_from']}〜{r['fetched_to']} "
                      f"ok={r.get('ok',0)} fail={r.get('fail',0)}")
        logger.info("%-20s %-10s %s", r["source"], r["status"], detail)
    logger.info("═" * 60)


if __name__ == "__main__":
    main()
