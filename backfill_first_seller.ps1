# =============================================================================
# MONO BACK OFFICE -- backfill_first_seller.ps1
#   Fetch 52 weeks of ファーストセラー data from ZOZO BO.
#   Reuses a single browser session for efficiency.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File backfill_first_seller.ps1
#   powershell -ExecutionPolicy Bypass -File backfill_first_seller.ps1 -StartMonday 2025-06-23 -EndMonday 2026-06-16
#
# 52W 1W目 = week of 2025-06-16 (Mon) -> TARGET_DATE = 2025-06-23 (next Monday)
# EndMonday = most recent Monday (default)
# =============================================================================
param(
    [string]$StartMonday = "2025-06-23",
    [string]$EndMonday   = "",
    [string]$SkipExisting = "1"
)

$ErrorActionPreference = "Continue"
$ROOT  = "C:\Users\Administrator\Downloads\system"
$PY    = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$PROJ  = "mono-back-office-system"
$LOGDIR = Join-Path $ROOT "logs"
if (-not (Test-Path $LOGDIR)) { New-Item -ItemType Directory -Path $LOGDIR -Force | Out-Null }
$STAMP  = (Get-Date).ToString("yyyyMMdd_HHmmss")
$LOG    = Join-Path $LOGDIR ("backfill_first_seller_" + $STAMP + ".log")

function Log($m) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
  Write-Output $line
  Add-Content -Path $LOG -Value $line -Encoding UTF8
}

# Compute most recent Monday if not specified
if ([string]::IsNullOrEmpty($EndMonday)) {
    $today = (Get-Date)
    $daysBack = ($today.DayOfWeek.value__ + 6) % 7  # Mon=0, Sun=6
    $EndMonday = $today.AddDays(-$daysBack).ToString("yyyy-MM-dd")
}

Log "===== BACKFILL FIRST_SELLER START: $StartMonday -> $EndMonday ====="

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

$script = Join-Path $ROOT "pipeline\scrapers\backfill_first_seller.py"
Log "Running: $PY $script $StartMonday $EndMonday"

& $PY $script $StartMonday $EndMonday 2>&1 | ForEach-Object {
    Log $_
}
$exitCode = $LASTEXITCODE

Log "===== BACKFILL FIRST_SELLER DONE (exit=$exitCode) ====="
exit $exitCode
