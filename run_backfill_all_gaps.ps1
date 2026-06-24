# =============================================================================
# ONE COMMAND to upload all missing data to BigQuery.
#
#   1. Detect every date whose orders import is missing / 0 / abnormally low,
#      AND every date whose performance (UU/CVR/fav) is missing or whose
#      critical shop (MONO-MART) is absent.
#   2a. Re-fetch + re-ingest the orders-gap dates (day-level = every part number).
#   2b. Re-fetch + re-ingest performance for the performance/shop-gap dates.
#   3. Re-run the check to confirm BigQuery is complete.
#
# Use this when you "want to upload all new items": it finds the gaps for you,
# so you don't have to know the dates. Safe to re-run (loader DELETE+INSERTs by
# sale_date -> no duplicates).
#
#   powershell -ExecutionPolicy Bypass -File run_backfill_all_gaps.ps1
#   powershell -ExecutionPolicy Bypass -File run_backfill_all_gaps.ps1 -Days 90
#
# ASCII-only on purpose (Windows PowerShell 5.1 mis-parses non-ASCII .ps1).
# =============================================================================
param(
  [int]$Days = 60,
  # Sources to re-fetch per missing date. Default fills sales-qty/amount/etc.
  # For max blank-fill (also UU/CVR/fav-rate): -Sources "orders,shipped,performance"
  [string]$Sources = "orders,shipped"
)

$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\Administrator\Downloads\system"
$PY   = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"

$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONIOENCODING = "utf-8"
$env:GOOGLE_APPLICATION_CREDENTIALS = Join-Path $ROOT "pipeline\sheets-sa-key.json"
$env:GOOGLE_CLOUD_PROJECT = "mono-back-office-system"
$env:GCP_PROJECT_ID = "mono-back-office-system"

# Secrets (Slack webhook etc.) - same as the daily run.
$secretsOut = & $PY (Join-Path $ROOT "pipeline\fetch_secrets.py") 2>$null
foreach ($line in $secretsOut) { if ($line -match "^(\w+)=(.+)$") { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] } }

$datesFile     = Join-Path $env:TEMP "bigquery_gap_dates.txt"
$perfDatesFile = Join-Path $env:TEMP "bigquery_gap_perf_dates.txt"

# --- 1) detect gaps -> write orders-gap dates and performance/shop-gap dates ---
Write-Output "===== STEP 1: detect missing dates (last $Days days) ====="
Push-Location (Join-Path $ROOT "pipeline")
& $PY (Join-Path $ROOT "pipeline\scrapers\check_data_gaps.py") "--days" $Days "--emit-dates" $datesFile "--emit-perf-dates" $perfDatesFile
Pop-Location

if (-not (Test-Path $datesFile)) { Write-Output "FATAL: gap check did not run (no creds? see errors above)."; exit 2 }
$dates = @(Get-Content $datesFile | Where-Object { $_ -match '^\d{4}-\d{2}-\d{2}$' })
$perfDates = @()
if (Test-Path $perfDatesFile) { $perfDates = @(Get-Content $perfDatesFile | Where-Object { $_ -match '^\d{4}-\d{2}-\d{2}$' }) }

if ($dates.Count -eq 0 -and $perfDates.Count -eq 0) {
  Write-Output "===== DONE: no gaps. BigQuery is already complete. Nothing to upload. ====="
  exit 0
}

# --- 2a) upload orders-gap dates (sales-qty / amount / etc.) ---
if ($dates.Count -gt 0) {
  Write-Output ("===== STEP 2a: uploading " + $dates.Count + " orders-gap date(s): " + ($dates -join ",") + " (sources=" + $Sources + ") =====")
  & (Join-Path $ROOT "run_recover_dates.ps1") -Dates $dates -Sources $Sources
} else {
  Write-Output "===== STEP 2a: no orders gaps. ====="
}

# --- 2b) upload performance/shop-gap dates (UU / CVR / fav-rate, incl. MONO-MART) ---
if ($perfDates.Count -gt 0) {
  Write-Output ("===== STEP 2b: uploading " + $perfDates.Count + " performance/shop-gap date(s): " + ($perfDates -join ",") + " (sources=performance) =====")
  & (Join-Path $ROOT "run_recover_dates.ps1") -Dates $perfDates -Sources "performance"
} else {
  Write-Output "===== STEP 2b: no performance/shop gaps. ====="
}

# --- 3) re-confirm ---
Write-Output "===== STEP 3: re-check after upload ====="
Push-Location (Join-Path $ROOT "pipeline")
& $PY (Join-Path $ROOT "pipeline\scrapers\check_data_gaps.py") "--days" $Days
$finalExit = $LASTEXITCODE
Pop-Location

if ($finalExit -eq 0) {
  Write-Output "===== SUCCESS: all dates now present in BigQuery. ====="
} else {
  Write-Output "===== PARTIAL: some dates still missing (likely ZOZO empty file -> use MANUAL-CSV path in run_recover_dates.ps1 header). ====="
}
exit $finalExit
