# =============================================================================
# 昨日(2026-06-20)までのデータ復旧。
#   受注/発送 : 6/19・6/20 を日付指定で正確に取得
#   在庫分析/倉庫在庫/予約 : スナップショット型のため実行時点の状態で最新化
# 各日: scrape → BigQuery ingest。アカウント連打を避け1日ずつ順次。
# =============================================================================
$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\Administrator\Downloads\system"
$PY   = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$LOG  = Join-Path $ROOT "logs\recover_to_yesterday.log"
function Log($m) { $line = "{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $m; Add-Content -Path $LOG -Value $line -Encoding UTF8 }

$env:PYTHONIOENCODING = "utf-8"
$env:GOOGLE_APPLICATION_CREDENTIALS = Join-Path $ROOT "pipeline\sheets-sa-key.json"
$env:GCS_RAW_BUCKET = "mono-back-office-system-raw-data"
$env:HEADLESS = "1"

# secrets (BASIC auth) + 正しいログインアカウントで上書き
$secretsOut = & $PY (Join-Path $ROOT "pipeline\fetch_secrets.py") 2>$null
foreach ($line in $secretsOut) { if ($line -match "^(\w+)=(.+)$") { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] } }
# 認証情報はローカル機密ファイル（secrets.local.ps1・gitignore）から読み込む。
if (Test-Path "$PSScriptRoot\secrets.local.ps1") { . "$PSScriptRoot\secrets.local.ps1" }

$ALL = "orders,shipped,stock_analysis,inventory_arrival,inventory_sku,reservations"
$days = @("2026-06-19", "2026-06-20")
Log "===== RECOVER START (to yesterday 2026-06-20) ====="
foreach ($d in $days) {
  Log "===== $d scrape ($ALL) ====="
  $env:TARGET_DATE = $d
  $env:ONLY = $ALL
  & $PY (Join-Path $ROOT "pipeline\scrapers\zozo_scraper.py") 2>&1 | ForEach-Object { Log $_ }
  Log "===== $d ingest ====="
  & $PY (Join-Path $ROOT "pipeline\main.py") "--csv-ingest" "--date" $d 2>&1 | ForEach-Object { Log $_ }
  Log "===== $d done ====="
  Start-Sleep -Seconds 5
}
Log "===== ALL DONE ====="
