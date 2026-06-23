# =============================================================================
# MONO BACK OFFICE - daily full automation
#   1) ZOZO scraping (9 sources -> GCS)
#   2) ETL ingest + mart rebuild (GCS -> BigQuery -> mart_layer.order_analysis)
# Server TZ = JST. Invoked daily by Task Scheduler. Manual run also OK:
#   powershell -ExecutionPolicy Bypass -File run_daily.ps1
# NOTE: ASCII-only on purpose (Windows PowerShell 5.1 mis-parses non-ASCII .ps1).
# =============================================================================
$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\Administrator\Downloads\system"
$PY   = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$PROJ = "mono-back-office-system"
$LOGDIR = Join-Path $ROOT "logs"
if (-not (Test-Path $LOGDIR)) { New-Item -ItemType Directory -Path $LOGDIR -Force | Out-Null }

# Target date = yesterday (server TZ is JST, so no conversion needed).
$TARGET = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")
$STAMP  = (Get-Date).ToString("yyyyMMdd_HHmmss")
$LOG    = Join-Path $LOGDIR ("daily_" + $STAMP + ".log")

function Log($m) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  Write-Output $line
  Add-Content -Path $LOG -Value $line -Encoding UTF8
}

Log "===== DAILY RUN START target=$TARGET ====="

# Refresh PATH from Machine+User so gcloud etc. resolve under Task Scheduler.
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONIOENCODING = "utf-8"

# Application Default Credentials for the Python google-cloud clients
# (storage / bigquery / secretmanager). Prefer ADC file; fall back to SA key.
$adc    = Join-Path $env:APPDATA "gcloud\application_default_credentials.json"
$saKey  = Join-Path $ROOT "pipeline\sheets-sa-key.json"
if (Test-Path $adc) {
  $env:GOOGLE_APPLICATION_CREDENTIALS = $adc
  Log "ADC set: $adc"
} elseif (Test-Path $saKey) {
  $env:GOOGLE_APPLICATION_CREDENTIALS = $saKey
  Log "ADC not found -- using SA key fallback: $saKey"
} else {
  Log "WARN: no GCP credentials found -- GCP clients will fail"
}
$env:GOOGLE_CLOUD_PROJECT = $PROJ

# --- Credentials from Secret Manager (Python SDK, no gcloud CLI required) ---
$secretsOutput = & $PY (Join-Path $ROOT "pipeline\fetch_secrets.py") 2>&1
$secretsExit   = $LASTEXITCODE
if ($secretsExit -ne 0) {
  Log "FATAL: secret fetch failed (exit=$secretsExit): $secretsOutput"
  exit 2
}
foreach ($line in $secretsOutput) {
  if ($line -match "^(\w+)=(.+)$") {
    [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2])
  }
}
# --- Correct ZOZO login account override (2026-06-19) ---
# Secret Manager still holds the OLD account (MONO-MART200), which now fails
# login ("login failed") and stopped all data collection on ~6/15. The correct
# account is <ZOZO_LOGIN_ID>. Override here until an admin updates the
# ZOZO_USER / ZOZO_PASS secrets (SA lacks secretmanager.versions.add).
# TODO: remove this block once Secret Manager is updated.
# 認証情報はローカル機密ファイル（secrets.local.ps1・gitignore）から読み込む。
if (Test-Path "$PSScriptRoot\secrets.local.ps1") { . "$PSScriptRoot\secrets.local.ps1" }
if (-not $env:ZOZO_BASIC_USER -or -not $env:ZOZO_LOGIN_ID) {
  Log "FATAL: credentials empty after secret fetch"
  exit 2
}

# --- 0) Incremental backfill (watermark-based, 仕様書 列F=2024/7/1 の6ソース) ---
# インクリメンタル取得: BigQuery の MAX(日付) を見て差分だけ取得する。
#
# 初回実行: BigQuery にデータなし → 2024-07-01 から昨日まで全件取得
# 翌日以降: MAX(日付)=昨日 → fetch_from > fetch_to → 自動スキップ
#
# --max-looker-days 90 = Looker系（No.8/19/20）の遡及上限（初回フル取得は 730 を指定）
# 受注・発送（No.1/2）は月次バッチのため上限なし。
$env:HEADLESS = "1"
Log "[0] incremental backfill start"
& $PY (Join-Path $ROOT "pipeline\scrapers\incremental_backfill.py") `
    "--max-looker-days" "90" 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Log "[0] incremental backfill done exit=$LASTEXITCODE"

# --- 1) Scraping (sequential to avoid ZOZO throttling) ---
# Now covers 11 sources: orders/shipped/reservations/inventory(sku+arrival)/
# stock_analysis/performance/product_master/sale_settings (existing 8) plus
# search_keyword (No.20) + access_log (No.19) added 2026-06-03.
# zozoad (No.7) and coupon (No.18) use dedicated fetchers below.
$env:HEADLESS = "1"
$env:PARALLEL_WORKERS = "1"
$env:MAX_RETRIES_PER_SOURCE = "2"
$env:RETRY_BACKOFF_BASE_SEC = "5"
$env:TARGET_DATE = $TARGET
Log "[1/2] scraping start"
& $PY (Join-Path $ROOT "pipeline\scrapers\zozo_scraper.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
$scrapeExit = $LASTEXITCODE
Log "[1/2] scraping done exit=$scrapeExit (partial failure is OK - ETL still runs)"

# --- 1b) MMS 原価 (No.10) — per-shop 評価額一覧 → GCS (no 2FA) ---
# Uses sessions/mms_state.json; auto re-logins via LOGIN_USER/LOGIN_PASS.
$env:LOGIN_USER = $env:MMS_LOGIN_USER  # secrets.local.ps1 から
$env:LOGIN_PASS = $env:MMS_LOGIN_PASS
Log "[1b] MMS cost fetch start"
& $PY (Join-Path $ROOT "pipeline\scrapers\fetch_mms_cost.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Log "[1b] MMS cost fetch done exit=$LASTEXITCODE (non-fatal - ETL still runs)"
Remove-Item Env:\LOGIN_USER, Env:\LOGIN_PASS -ErrorAction SilentlyContinue

# --- 1b2) MMS 発注書一覧 (No.49) — 前回発注日・前回原価 用 → analytics_layer.mms_orders ---
# Scrapes order_list.php (発注日 既定550日遡及), writes GCS + BigQuery (WRITE_TRUNCATE).
# Self-contained load (no main.py ETL step). Uses MMS LOGIN_USER/LOGIN_PASS. Non-fatal.
$env:LOGIN_USER = $env:MMS_LOGIN_USER
$env:LOGIN_PASS = $env:MMS_LOGIN_PASS
Log "[1b2] MMS orders fetch start"
& $PY (Join-Path $ROOT "pipeline\scrapers\fetch_mms_orders.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Log "[1b2] MMS orders fetch done exit=$LASTEXITCODE (non-fatal - ETL still runs)"
Remove-Item Env:\LOGIN_USER, Env:\LOGIN_PASS -ErrorAction SilentlyContinue

# --- 1c) Google Sheets (PF fee + hacchu / nyuukazan) — SA auth, no 2FA ---
# Reads two client-shared sheets via sheets-fetcher@... SA and uploads CSV
# to gs://.../uploads/sheets/pf_fee/ and gs://.../uploads/tableau/hacchu/.
Log "[1c] Sheets fetch start (pf_fee, hacchu)"
& $PY (Join-Path $ROOT "pipeline\scrapers\fetch_sheets.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Log "[1c] Sheets fetch done exit=$LASTEXITCODE (non-fatal - ETL still runs)"

# --- 1d) Weekly: ファーストセラー (Mondays only, fetches previous ISO week) ---
# Client spec 2026-05-29: Mon-Sun ISO week, top 50 per (gender). Skip non-Mon.
if ((Get-Date).DayOfWeek -eq [DayOfWeek]::Monday) {
  Log "[1d] First Seller fetch start (Mon - previous ISO week)"
  & $PY (Join-Path $ROOT "pipeline\scrapers\fetch_first_seller.py") 2>&1 |
    ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
  Log "[1d] First Seller fetch done exit=$LASTEXITCODE"
} else {
  Log "[1d] First Seller skipped (not Monday)"
}

# --- 1e) No.18 クーポン除外 (EventCalendar.asp) ---
# クーポン施策日のみ存在。なければ no-op で正常終了。
# Output: gs://.../uploads/zozo/coupon/{date}/{brand}_yyyymmdd.csv (cp932)
Log "[1e] Coupon exclusion fetch start"
& $PY (Join-Path $ROOT "pipeline\scrapers\fetch_coupon_exclusion.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Log "[1e] Coupon exclusion fetch done exit=$LASTEXITCODE (non-fatal - no events = OK)"

# --- 1f) No.7 ZOZOAD は 07:00 では取得しない ---
# ZOZO BO の広告実績は ~11:00 JST に当日反映される。07:00 時点では前日分も
# 完全には確定していないため、別タスク (MONO-BackOffice-ZOZOAD-Noon) で
# 12:30 JST に取得+ingest する。`run_zozoad_noon.ps1` を参照。
Log "[1f] ZOZOAD skipped (handled by noon task at 12:30 JST)"

# --- 1g) No.15 Product reviews (GoodsReview.asp per-shop HTML scrape) ---
# Output: gs://.../uploads/zozo/reviews/{date}/reviews.csv (UTF-8 BOM)
Log "[1g] Product reviews fetch start"
& $PY (Join-Path $ROOT "pipeline\scrapers\fetch_product_reviews.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Log "[1g] Product reviews fetch done exit=$LASTEXITCODE (non-fatal - no reviews on target date = OK)"

# --- 1h) Sitateru item list (smart 3-layer search: 24 base -> expand if >2000) ---
# Strategy: division x season x status (24 queries)
#   Layer 2 (>2000 hits): + display_flag (up to 120 queries)
#   Layer 3 (>2000 hits): + order_type  (up to 1080 queries)
# Output: gs://.../uploads/sitateru/itemlist/{date}/item_list_{yyyymmdd}.csv
# ETL:    analytics_layer.sitateru_item_master (via main.py --csv-ingest)
# Auth:   sessions/sitateru_state.json -> SITATERU_USER/PASS fallback (from Secret Manager)
# Email:  IMAP_USER hardcoded; IMAP_PASS from Secret Manager (secret name: IMAP_PASS)
$env:IMAP_USER = "yujin-yamaguchi@mono-mart.jp"
# IMAP_PASS injected by fetch_secrets.py if stored in Secret Manager.
# Fallback: hardcoded here so daily runs work even without Secret Manager access.
# IMAP_PASS は secrets.local.ps1 / Secret Manager から供給される。
Log "[1h] Sitateru item list fetch start (IMAP_USER=$($env:IMAP_USER) IMAP_PASS_set=$(-not [string]::IsNullOrEmpty($env:IMAP_PASS)))"
& $PY (Join-Path $ROOT "pipeline\scrapers\fetch_sitateru.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Log "[1h] Sitateru item list fetch done exit=$LASTEXITCODE (non-fatal)"

# --- 2) ETL ingest + mart rebuild (runs even if some scrapes failed) ---
Log "[2/2] ETL + mart refresh start"
Push-Location (Join-Path $ROOT "pipeline")
& $PY "main.py" --csv-ingest --date $TARGET 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
$etlExit = $LASTEXITCODE
Pop-Location
Log "[2/2] ETL done exit=$etlExit"

# --- 3a) Generate sale_settings CSV from product_master (price_type='セール') ---
# Workaround for ZOZO BO not exposing セール設定 CSV directly: extract sale
# items from the daily goods_cs.csv (product_master) and write a salegoods.csv
# to the standard sale path so the existing csv_sale_settings ETL step can
# pick it up on the next ingest pass.
Log "[3a] Sale settings CSV generation start"
& $PY (Join-Path $ROOT "pipeline\scrapers\generate_sale_settings_csv.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Log "[3a] Sale settings CSV done exit=$LASTEXITCODE"

# --- 3b) Re-run csv-ingest to pick up the newly generated salegoods.csv ---
# product_master has to be in BigQuery first (Step [2]) for [3a] to extract
# from it; this second ingest pass then loads salegoods.csv into BigQuery.
Log "[3b] Sale settings ingest start"
Push-Location (Join-Path $ROOT "pipeline")
& $PY "main.py" --csv-ingest --date $TARGET 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Pop-Location
Log "[3b] Sale settings ingest done exit=$LASTEXITCODE"

# --- 3c) Generate verify report (HTML uploaded to GCS for client review) ---
Log "[3c] Verify report generation start"
& $PY (Join-Path $ROOT "pipeline\scrapers\generate_verify_report.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Log "[3c] Verify report done exit=$LASTEXITCODE (URL: https://storage.googleapis.com/mono-back-office-system-exports/verify/index.html)"

# --- 3d) Generate 発注管理表 Excel (Phase 2 - dated + latest URL) ---
Log "[3d] Order management Excel generation start"
& $PY (Join-Path $ROOT "pipeline\scrapers\generate_order_excel.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
Log "[3d] Order Excel done exit=$LASTEXITCODE (latest: https://storage.googleapis.com/mono-back-office-system-exports/order_management/latest/%E7%99%BA%E6%B3%A8%E7%AE%A1%E7%90%86%E8%A1%A8.xlsx)"

# --- 3e) Data-gap monitor: flag dates whose orders import is missing / 0 / too low ---
# Catches the "success but 0 rows" case (e.g. 2026-06-21/06-22) that step-level
# failure alerts miss. Records to monitoring + Slack; non-fatal to the daily run.
Log "[3e] Data-gap check start"
Push-Location (Join-Path $ROOT "pipeline")
& $PY (Join-Path $ROOT "pipeline\scrapers\check_data_gaps.py") "--days" 35 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
$gapExit = $LASTEXITCODE
Pop-Location
Log "[3e] Data-gap check done exit=$gapExit (1 = gaps detected -> see Slack / log)"

Log "===== DAILY RUN END scrape=$scrapeExit etl=$etlExit gaps=$gapExit ====="

# Prune logs older than 30 days.
Get-ChildItem $LOGDIR -Filter "daily_*.log" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
  Remove-Item -Force -ErrorAction SilentlyContinue

if ($etlExit -ne 0) { exit 1 } else { exit 0 }
