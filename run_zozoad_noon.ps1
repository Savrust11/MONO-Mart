# =============================================================================
# MONO BACK OFFICE - ZOZOAD noon fetcher
# ZOZO BO publishes ad performance numbers around 11:00 JST. The morning
# (07:00) daily run is too early, so this fetcher runs at 12:30 JST to grab
# the previous day's confirmed data (T-1) and ingest it into BigQuery.
#
# Manual run: powershell -ExecutionPolicy Bypass -File run_zozoad_noon.ps1
# =============================================================================
$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\Administrator\Downloads\system"
$PY   = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$PROJ = "mono-back-office-system"
$LOGDIR = Join-Path $ROOT "logs"
if (-not (Test-Path $LOGDIR)) { New-Item -ItemType Directory -Path $LOGDIR -Force | Out-Null }

$TARGET = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")
$STAMP  = (Get-Date).ToString("yyyyMMdd_HHmmss")
$LOG    = Join-Path $LOGDIR ("zozoad_noon_" + $STAMP + ".log")

function Log($m) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  Write-Output $line
  Add-Content -Path $LOG -Value $line -Encoding UTF8
}

Log "===== ZOZOAD NOON RUN START target=$TARGET ====="

$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONIOENCODING = "utf-8"

$adc   = Join-Path $env:APPDATA "gcloud\application_default_credentials.json"
$saKey = Join-Path $ROOT "pipeline\sheets-sa-key.json"
if (Test-Path $adc) {
  $env:GOOGLE_APPLICATION_CREDENTIALS = $adc
  Log "ADC set: $adc"
} elseif (Test-Path $saKey) {
  $env:GOOGLE_APPLICATION_CREDENTIALS = $saKey
  Log "ADC not found -- using SA key fallback: $saKey"
} else {
  Log "WARN: no GCP credentials found"
}
$env:GOOGLE_CLOUD_PROJECT = $PROJ

# Secrets (Python SDK, no gcloud CLI required)
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

# T-1 day data (ZOZO_LAG_DAYS=1 in fetcher → fetch_date = TARGET - 1 = today-2).
# Wait — running at 12:30 JST today, TARGET = yesterday. fetcher subtracts 1
# day more → fetch_date = day-before-yesterday. Reset ZOZOAD_LAG_DAYS=0 here
# so the fetcher uses TARGET as-is (T-1 from a "today" perspective).
$env:ZOZOAD_LAG_DAYS = "0"
$env:TARGET_DATE = $TARGET
$env:HEADLESS = "1"

Log "[1] ZOZOAD fetch start (target=$TARGET, lag=0 since noon-task)"
& $PY (Join-Path $ROOT "pipeline\scrapers\fetch_zozoad_report.py") 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
$fetchExit = $LASTEXITCODE
Log "[1] ZOZOAD fetch done exit=$fetchExit"

# Re-run csv-ingest to load the freshly-uploaded ZOZOAD data into BQ. The
# zozoad ETL step scans all date subfolders so it picks up the new file.
Log "[2] ETL csv-ingest (re-run to load new ZOZOAD data)"
Push-Location (Join-Path $ROOT "pipeline")
& $PY "main.py" --csv-ingest --date $TARGET 2>&1 |
  ForEach-Object { Add-Content -Path $LOG -Value $_ -Encoding UTF8 }
$etlExit = $LASTEXITCODE
Pop-Location
Log "[2] ETL done exit=$etlExit"

Log "===== ZOZOAD NOON RUN END fetch=$fetchExit etl=$etlExit ====="

# Prune logs older than 30 days
Get-ChildItem $LOGDIR -Filter "zozoad_noon_*.log" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
  Remove-Item -Force -ErrorAction SilentlyContinue

if ($etlExit -ne 0) { exit 1 } else { exit 0 }
