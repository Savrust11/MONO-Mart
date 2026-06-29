#!/bin/bash
# =============================================================================
# MONO BACK OFFICE — daily acquisition (Linux fallback for the stalled X server)
#   Fetches the PREVIOUS DAY from ZOZO -> GCS -> BigQuery -> mart, then gap-check.
#   Installed via cron at 07:30 JST. Idempotent (analytics upserts DELETE+INSERT
#   by date). Box TZ is JST, so TARGET = yesterday with no conversion.
# =============================================================================
set -uo pipefail
ROOT=/home/myuser/Downloads/system
cd "$ROOT" || exit 3
source .venv/bin/activate
source .zozo_env.sh
[ -f "$ROOT/.alert_env.sh" ] && source "$ROOT/.alert_env.sh"   # ALERT_WEBHOOK_URL（gitignore）
export GOOGLE_APPLICATION_CREDENTIALS="$ROOT/pipeline/sheets-sa-key.json"
export GOOGLE_CLOUD_PROJECT=mono-back-office-system GCP_PROJECT_ID=mono-back-office-system
export GCS_RAW_BUCKET=mono-back-office-system-raw-data
export HEADLESS=1 PARALLEL_WORKERS=1 MAX_RETRIES_PER_SOURCE=2

TARGET="${1:-$(date -d 'yesterday' +%F)}"     # arg1 overrides; default = yesterday (JST)
LOGDIR="$ROOT/logs"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/linux_daily_$(date +%Y%m%d_%H%M%S).log"
exec >>"$LOG" 2>&1
echo "===== LINUX DAILY START target=$TARGET  $(date) ====="

# 1) Scrape the target day (core daily sources). Per-source failure is non-fatal.
echo "----- [1] scrape -----"
TARGET_DATE="$TARGET" \
ONLY="orders,shipped,reservations,stock_analysis,inventory_sku,inventory_arrival,performance,product_master,sale_settings" \
  timeout 2400 python pipeline/scrapers/zozo_scraper.py
echo "[1] scrape exit=$?"

# 1b) ZOZOAD（広告実績）は専用フェッチャ。成功マーカーで二重取得防止・失敗時のみ再取得。
echo "----- [1b] zozoad fetch -----"
TARGET_DATE="$TARGET" timeout 900 python pipeline/scrapers/fetch_zozoad_report.py || true
echo "[1b] zozoad exit=$?"

# 1c) Googleシート（発注明細→入荷残・PF手数料・買い回り）。SAキーで取得→GCS。
#     これが未実行だと入荷残(incoming_stock)が更新されず古いまま固定される不具合があったため日次化。
echo "----- [1c] sheets fetch (発注明細/PF) -----"
TARGET_DATE="$TARGET" timeout 600 python pipeline/scrapers/fetch_sheets.py || true
echo "[1c] sheets exit=$?"

# 2) ETL ingest (GCS -> BigQuery analytics layer; idempotent DELETE+INSERT by date)
echo "----- [2] ingest -----"
timeout 1200 python pipeline/main.py --csv-ingest --date "$TARGET"
echo "[2] ingest exit=$?"

# 3) Explicit mart rebuild (main.py's mart step is wrapped non-blocking & can no-op)
echo "----- [3] mart refresh -----"
python - "$ROOT" "$TARGET" <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.join(sys.argv[1], "pipeline"))
from loaders.bigquery_loader import BigQueryLoader
from transformers.kpi_calculator import run_mart_refresh
try:
    run_mart_refresh(BigQueryLoader(project="mono-back-office-system"), sys.argv[2]); print("[3] mart OK")
except Exception as e:
    print("[3] mart FAIL:", e)
PYEOF

# 4) Gap monitor (surfaces missing/low dates so silent failures become visible)
echo "----- [4] gap check -----"
timeout 300 python pipeline/scrapers/check_data_gaps.py 2>&1 | tail -30 || true

# 5) Alert — verify the target day landed, post status to webhook (success+failure)
echo "----- [5] notify -----"
timeout 120 python pipeline/notify_daily.py "$TARGET"
echo "[5] notify exit=$?"

# 6) Data freshness dashboard + alert（UU/performance等が遅延/停止したら通知。ZOZO追いつき次第自動回復）
echo "----- [6] freshness -----"
timeout 180 python pipeline/data_freshness.py --alert || true
echo "[6] freshness exit=$?"

echo "===== LINUX DAILY DONE  $(date) ====="
