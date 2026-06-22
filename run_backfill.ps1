# =============================================================================
# MONO BACK OFFICE - 2-year historical data backfill
#
# Client requirement: Collect order data from 2024-07-01 onward.
#
# HOW IT WORKS
# ------------
# ZOZO BO's web UI only exposes the last 1 year of data.
# As of June 2026 that means:
#
#   [PHASE A] July 2025 ~ June 2026   -> accessible via ZOZO BO, this script
#                                        downloads + ingests month by month
#   [PHASE B] July 2024 ~ June 2025   -> older than 1 year; ZOZO BO UI
#                                        cannot access this. Requires a
#                                        separate bulk export from ZOZO
#                                        partner support. See instructions
#                                        below under PHASE B INSTRUCTIONS.
#
# USAGE
# -----
#   powershell -ExecutionPolicy Bypass -File run_backfill.ps1
#
# To run only Phase A (accessible period):
#   powershell -ExecutionPolicy Bypass -File run_backfill.ps1 -PhaseA
#
# To run only Phase B ingest (after uploading ZOZO export to GCS manually):
#   powershell -ExecutionPolicy Bypass -File run_backfill.ps1 -PhaseB
#
# =============================================================================
param(
    [switch]$PhaseA,
    [switch]$PhaseB,
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$ROOT   = "C:\Users\Administrator\Downloads\system"
$PY     = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$PROJ   = "mono-back-office-system"
$LOGDIR = Join-Path $ROOT "logs"
if (-not (Test-Path $LOGDIR)) { New-Item -ItemType Directory -Path $LOGDIR -Force | Out-Null }

$STAMP = (Get-Date).ToString("yyyyMMdd_HHmmss")
$LOG   = Join-Path $LOGDIR ("backfill_" + $STAMP + ".log")

function Log($m) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  Write-Output $line
  Add-Content -Path $LOG -Value $line -Encoding UTF8
}

Log "===== BACKFILL START ====="
Log "Log: $LOG"
if ($DryRun) { Log "[DRY RUN MODE - no actual downloads or ETL]" }

# Refresh PATH (needed when run from Task Scheduler)
$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONIOENCODING = "utf-8"
$env:GOOGLE_CLOUD_PROJECT = $PROJ

# GCP credentials
$adc   = Join-Path $env:APPDATA "gcloud\application_default_credentials.json"
$saKey = Join-Path $ROOT "pipeline\sheets-sa-key.json"
if (Test-Path $adc) {
  $env:GOOGLE_APPLICATION_CREDENTIALS = $adc
  Log "ADC: $adc"
} elseif (Test-Path $saKey) {
  $env:GOOGLE_APPLICATION_CREDENTIALS = $saKey
  Log "SA key: $saKey"
} else {
  Log "WARN: no GCP credentials found"
}

# Fetch ZOZO credentials from Secret Manager
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

$env:HEADLESS = "1"
$SCRAPER = Join-Path $ROOT "pipeline\scrapers\backfill_orders.py"

# ── Decide which phases to run ────────────────────────────────────────────────
$RunA = (-not $PhaseB)  # default: run A unless -PhaseB only
$RunB = (-not $PhaseA)  # default: run B unless -PhaseA only
if ($PhaseA -and -not $PhaseB) { $RunA = $true;  $RunB = $false }
if ($PhaseB -and -not $PhaseA) { $RunA = $false; $RunB = $true  }

# =============================================================================
# PHASE A: July 2025 ~ June 2026 (accessible via ZOZO BO)
# =============================================================================
if ($RunA) {
  Log ""
  Log "===== PHASE A: July 2025 ~ June 2026 (ZOZO BO UI - last 1 year) ====="
  Log "Downloads monthly order/shipped CSVs and ingests into BigQuery."

  $phaseAArgs = @(
    "--start-date", "2025-07-01",
    "--end-date",   (Get-Date).ToString("yyyy-MM-dd"),
    "--sources",    "orders,shipped"
  )
  if ($DryRun) { $phaseAArgs += "--dry-run" }

  Push-Location (Join-Path $ROOT "pipeline\scrapers")
  & $PY $SCRAPER @phaseAArgs 2>&1 | ForEach-Object {
    Add-Content -Path $LOG -Value $_ -Encoding UTF8
    Write-Output $_
  }
  $exitA = $LASTEXITCODE
  Pop-Location
  Log "Phase A done. exit=$exitA"
}

# =============================================================================
# PHASE B: July 2024 ~ June 2025 (pre-2025 data — ingest only)
# =============================================================================
if ($RunB) {
  Log ""
  Log "===== PHASE B: July 2024 ~ June 2025 (pre-2025 historical) ====="

  # Check whether pre-2025 GCS files exist by listing the bucket
  $bucket    = "mono-back-office-system-raw-data"
  $testBlob  = "uploads/zozo/orders/2024-07-01/"
  $blobCheck = & gcloud storage ls "gs://$bucket/$testBlob" 2>&1
  $hasData   = ($LASTEXITCODE -eq 0 -and $blobCheck -ne "")

  if ($hasData) {
    Log "Pre-2025 CSV files found in GCS. Running --only-ingest."
    $phaseBArgs = @(
      "--start-date", "2024-07-01",
      "--end-date",   "2025-06-30",
      "--only-ingest"
    )
    if ($DryRun) { $phaseBArgs += "--dry-run" }

    Push-Location (Join-Path $ROOT "pipeline\scrapers")
    & $PY $SCRAPER @phaseBArgs 2>&1 | ForEach-Object {
      Add-Content -Path $LOG -Value $_ -Encoding UTF8
      Write-Output $_
    }
    $exitB = $LASTEXITCODE
    Pop-Location
    Log "Phase B done. exit=$exitB"
  } else {
    Log ""
    Log "  ⚠️  PHASE B REQUIRES MANUAL ACTION — READ CAREFULLY"
    Log "  ──────────────────────────────────────────────────────────────────"
    Log "  July 2024 ~ June 2025 data is OLDER THAN 1 YEAR and cannot be"
    Log "  downloaded via the ZOZO BO web UI."
    Log ""
    Log "  ACTION REQUIRED:"
    Log "  1. Contact ZOZO partner support and request a bulk CSV export:"
    Log "       - Data type : 注文 (orders) + 発送 (shipped)"
    Log "       - Date range: 2024-07-01 ~ 2025-06-30"
    Log "       - Format    : same as the standard BO CSV download (cp932)"
    Log ""
    Log "  2. When received, organize by month and upload to GCS:"
    Log "       gs://mono-back-office-system-raw-data/uploads/zozo/orders/2024-07-01/2024_07_orders.csv"
    Log "       gs://mono-back-office-system-raw-data/uploads/zozo/orders/2024-08-01/2024_08_orders.csv"
    Log "       ...through..."
    Log "       gs://mono-back-office-system-raw-data/uploads/zozo/orders/2025-06-01/2025_06_orders.csv"
    Log "     (same structure for shipped CSVs under .../zozo/shipped/...)"
    Log ""
    Log "       Upload command (per file):"
    Log "       gcloud storage cp 2024_07_orders.csv gs://mono-back-office-system-raw-data/uploads/zozo/orders/2024-07-01/"
    Log ""
    Log "  3. Re-run this script with -PhaseB flag to trigger ETL ingest:"
    Log "       powershell -File run_backfill.ps1 -PhaseB"
    Log "  ──────────────────────────────────────────────────────────────────"
    Log "  Phase B skipped (no pre-2025 CSV files found in GCS)."
  }
}

# =============================================================================
# VERIFICATION QUERY (after both phases complete)
# =============================================================================
if (-not $DryRun) {
  Log ""
  Log "===== VERIFICATION ====="
  Log "Run the following BigQuery query to confirm data coverage:"
  Log ""
  Log "  SELECT"
  Log "    DATE_TRUNC(sale_date, MONTH) AS month,"
  Log "    COUNT(*)                     AS rows,"
  Log "    SUM(sales_quantity)          AS total_orders,"
  Log "    SUM(sales_amount)            AS total_amount_excl_tax"
  Log "  FROM \`mono-back-office-system.analytics_layer.sales_daily\`"
  Log "  WHERE sale_date BETWEEN '2024-07-01' AND CURRENT_DATE('Asia/Tokyo')"
  Log "  GROUP BY 1"
  Log "  ORDER BY 1"
  Log ""
  Log "Expected: rows for every month from 2024-07 onward."
  Log "Any month with 0 rows = data still missing for that period."
  Log ""
  Log "Dashboard URL (after backfill completes):"
  Log "  https://storage.googleapis.com/mono-back-office-system-exports/verify/index.html"
  Log "  -> 'データ範囲' column should show earliest date = 2024-07-xx"
}

Log ""
Log "===== BACKFILL END ====="
