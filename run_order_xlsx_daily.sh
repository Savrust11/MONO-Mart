#!/bin/bash
# 発注管理表.xlsx を毎朝 BigQuery から生成して GCS へアップロード（Option A・Linux側）。
# ZOZO取得に依存しないので私の環境で確実に動く。Xサーバ(Windows)の停止に影響されない。
cd /home/myuser/Downloads/system
source .venv/bin/activate
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/pipeline/sheets-sa-key.json"
LOG="$PWD/logs/order_xlsx_$(date +%Y%m%d_%H%M%S).log"
{ echo "===== ORDER XLSX START $(date) ====="
  timeout 600 python pipeline/build_order_xlsx.py
  echo "===== ORDER XLSX DONE exit=$? ====="; } >> "$LOG" 2>&1
