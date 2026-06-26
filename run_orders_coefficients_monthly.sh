#!/bin/bash
# 月次 季節係数 再構築（毎月1日cron）。受注が貯まるほど精度向上。対策C。
# first_seller の週次cronとは別物（seasonal_coefficients を作るのはこのスクリプトのみ）。
cd /home/myuser/Downloads/system
source .venv/bin/activate
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/pipeline/sheets-sa-key.json"
LOG="$PWD/logs/orders_coefficients_$(date +%Y%m%d_%H%M%S).log"
{ echo "===== ORDERS COEF START $(date) ====="
  timeout 600 python pipeline/build_orders_coefficients.py
  echo "--- elapsed (経過係数) ---"
  timeout 600 python pipeline/build_elapsed_coefficients.py
  echo "===== ORDERS COEF DONE exit=$? ====="; } >> "$LOG" 2>&1
