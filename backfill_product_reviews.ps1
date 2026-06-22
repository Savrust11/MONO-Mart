# =============================================================================
# MONO BACK OFFICE -- backfill_product_reviews.ps1
#   Fetch all available historical review data from ZOZO BO (up to 1 year back).
#   Reuses a single browser session for efficiency.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File backfill_product_reviews.ps1
#   powershell -ExecutionPolicy Bypass -File backfill_product_reviews.ps1 -StartDate 2025-06-17 -EndDate 2026-06-16
#
# Options:
#   -StartDate  First date to fetch (default: 2025-06-17, 1 year ago)
#   -EndDate    Last  date to fetch (default: yesterday)
#   -SkipExisting  0 to re-fetch dates already in GCS (default: 1 = skip)
# =============================================================================
param(
    [string]$StartDate = "2025-06-17",
    [string]$EndDate   = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd"),
    [string]$SkipExisting = "1"
)

$ErrorActionPreference = "Continue"
$ROOT  = "C:\Users\Administrator\Downloads\system"
$PY    = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$PROJ  = "mono-back-office-system"
$LOGDIR = Join-Path $ROOT "logs"
if (-not (Test-Path $LOGDIR)) { New-Item -ItemType Directory -Path $LOGDIR -Force | Out-Null }
$STAMP  = (Get-Date).ToString("yyyyMMdd_HHmmss")
$LOG    = Join-Path $LOGDIR ("backfill_reviews_" + $STAMP + ".log")

function Log($m) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  Write-Output $line
  Add-Content -Path $LOG -Value $line -Encoding UTF8
}

Log "===== BACKFILL REVIEWS START: $StartDate -> $EndDate ====="

$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONIOENCODING = "utf-8"

$adc   = Join-Path $env:APPDATA "gcloud\application_default_credentials.json"
$saKey = Join-Path $ROOT "pipeline\sheets-sa-key.json"
if (Test-Path $adc) {
    $env:GOOGLE_APPLICATION_CREDENTIALS = $adc
} elseif (Test-Path $saKey) {
    $env:GOOGLE_APPLICATION_CREDENTIALS = $saKey
    Log "Using SA key fallback"
} else {
    Log "WARN: no GCP credentials found"
}
$env:GOOGLE_CLOUD_PROJECT = $PROJ

$secretsOutput = & $PY (Join-Path $ROOT "pipeline\fetch_secrets.py") 2>&1
if ($LASTEXITCODE -ne 0) {
    Log "FATAL: secret fetch failed: $secretsOutput"
    exit 2
}
foreach ($line in $secretsOutput) {
    if ($line -match "^(\w+)=(.+)$") {
        [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2])
    }
}
if (-not $env:ZOZO_BASIC_USER -or -not $env:ZOZO_LOGIN_ID) {
    Log "FATAL: credentials empty after secret fetch"
    exit 2
}

$env:HEADLESS = "1"
$env:SKIP_EXISTING = $SkipExisting

$script = Join-Path $ROOT "pipeline\scrapers\backfill_product_reviews.py"
Log "Running: $PY $script $StartDate $EndDate"

& $PY $script $StartDate $EndDate 2>&1 | ForEach-Object {
    Log $_
}
$exitCode = $LASTEXITCODE

Log "===== BACKFILL REVIEWS DONE (exit=$exitCode) ====="
exit $exitCode
