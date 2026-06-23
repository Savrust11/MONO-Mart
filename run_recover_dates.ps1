# =============================================================================
# Backfill specific dates: re-fetch (orders,shipped) + re-ingest, to fix the
# missing 販売数/金額. Idempotent: the BigQuery loader does DELETE+INSERT by
# sale_date, so re-running replaces partial data (no duplicates).
#
#   Default = the 4 dates the customer flagged:
#     powershell -ExecutionPolicy Bypass -File run_recover_dates.ps1
#   Custom dates:
#     powershell -ExecutionPolicy Bypass -File run_recover_dates.ps1 -Dates "2026-05-23","2026-05-24"
#
# NOTE: ASCII-only on purpose (Windows PowerShell 5.1 mis-parses non-ASCII .ps1).
# =============================================================================
param([string[]]$Dates = @("2026-05-23","2026-05-24","2026-06-21","2026-06-22"))

$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\Administrator\Downloads\system"
$PY   = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$LOG  = Join-Path $ROOT "logs\recover_dates.log"
function Log($m) { $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m; Write-Output $line; Add-Content -Path $LOG -Value $line -Encoding UTF8 }

$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONIOENCODING = "utf-8"
$env:GOOGLE_APPLICATION_CREDENTIALS = Join-Path $ROOT "pipeline\sheets-sa-key.json"
$env:GOOGLE_CLOUD_PROJECT = "mono-back-office-system"
$env:GCS_RAW_BUCKET = "mono-back-office-system-raw-data"
$env:HEADLESS = "1"

# Secret Manager creds + ZOZO login override (same as run_daily.ps1)
$secretsOut = & $PY (Join-Path $ROOT "pipeline\fetch_secrets.py") 2>$null
foreach ($line in $secretsOut) { if ($line -match "^(\w+)=(.+)$") { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] } }
if (Test-Path "$PSScriptRoot\secrets.local.ps1") { . "$PSScriptRoot\secrets.local.ps1" }
if (-not $env:ZOZO_LOGIN_ID) { Log "FATAL: ZOZO credentials empty after secret fetch"; exit 2 }

Log ("===== BACKFILL START dates=" + ($Dates -join ",") + " =====")
foreach ($d in $Dates) {
  Log "----- $d : re-fetch (orders,shipped) -----"
  $env:TARGET_DATE = $d
  $env:ONLY = "orders,shipped"
  & $PY (Join-Path $ROOT "pipeline\scrapers\zozo_scraper.py") 2>&1 | ForEach-Object { Log $_ }
  Log "----- $d : re-ingest (DELETE+INSERT by sale_date) -----"
  & $PY (Join-Path $ROOT "pipeline\main.py") "--csv-ingest" "--date" $d 2>&1 | ForEach-Object { Log $_ }
  Log "----- $d done (exit=$LASTEXITCODE) -----"
  Start-Sleep -Seconds 5
}
Log "===== BACKFILL DONE ====="
