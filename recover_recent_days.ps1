# =============================================================================
# 直近の停止期間 (2026-06-16〜18) を取り戻す。アカウント修正(<ZOZO_LOGIN_ID>)後の復旧。
# 対象ソース: orders, shipped, stock_analysis (実証済みの中核ソース)
# 各日: スクレイプ → BigQuery取込。アカウント連打を避け1日ずつ順次。
# =============================================================================
$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\Administrator\Downloads\system"
$PY   = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$LOG  = Join-Path $ROOT "logs\recover_recent.log"
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

$days = @("2026-06-16","2026-06-17","2026-06-18")
foreach ($d in $days) {
  Log "===== $d scrape開始 ====="
  $env:TARGET_DATE = $d
  $env:ONLY = "orders,shipped,stock_analysis"
  & $PY (Join-Path $ROOT "pipeline\scrapers\zozo_scraper.py") 2>&1 | ForEach-Object { Log $_ }
  Log "===== $d 取込(ingest)開始 ====="
  & $PY (Join-Path $ROOT "pipeline\main.py") "--csv-ingest" "--date" $d 2>&1 | ForEach-Object { Log $_ }
  Log "===== $d 完了 ====="
  Start-Sleep -Seconds 5
}
Log "===== ALL DONE ====="
