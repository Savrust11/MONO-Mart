#!/bin/bash
# 週次ファーストセラー取得（毎週月曜cron）。直近3週をSKIP_EXISTINGで取得＝取りこぼし防止。
cd /home/myuser/Downloads/system
source .venv/bin/activate
source .zozo_env.sh
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/pipeline/sheets-sa-key.json"
export GCS_RAW_BUCKET="mono-back-office-system-raw-data" HEADLESS="1" SKIP_EXISTING="1"
LOG="$PWD/logs/first_seller_weekly_$(date +%Y%m%d_%H%M%S).log"
START=$(date -d '21 days ago' +%F)
{ echo "===== FS WEEKLY START $(date) (from $START) ====="
  timeout 1200 python pipeline/scrapers/backfill_first_seller.py "$START"
  echo "===== FS WEEKLY DONE exit=$? ====="; } >> "$LOG" 2>&1
