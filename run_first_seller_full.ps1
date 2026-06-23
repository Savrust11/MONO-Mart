# =============================================================================
# Run First Seller in FULL mode (gender x product-type x type) with the SAME
# environment run_daily.ps1 uses. Defaults to a SMALL validation run.
#
#   Validation (5 combos, saves locally only, no GCS overwrite):
#     powershell -ExecutionPolicy Bypass -File run_first_seller_full.ps1
#
#   Full run (all ~1,700 combos, uploads to GCS, can take a few hours):
#     powershell -ExecutionPolicy Bypass -File run_first_seller_full.ps1 -Limit 0
#
# NOTE: ASCII-only on purpose (Windows PowerShell 5.1 mis-parses non-ASCII .ps1).
# =============================================================================
param([int]$Limit = 5)

$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\Administrator\Downloads\system"
$PY   = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$PROJ = "mono-back-office-system"

$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONIOENCODING = "utf-8"

# GCP Application Default Credentials (for Secret Manager / GCS / BigQuery)
$adc   = Join-Path $env:APPDATA "gcloud\application_default_credentials.json"
$saKey = Join-Path $ROOT "pipeline\sheets-sa-key.json"
if (Test-Path $adc)       { $env:GOOGLE_APPLICATION_CREDENTIALS = $adc }
elseif (Test-Path $saKey) { $env:GOOGLE_APPLICATION_CREDENTIALS = $saKey }
$env:GOOGLE_CLOUD_PROJECT = $PROJ

# Credentials from Secret Manager + ZOZO override (same as run_daily.ps1)
$secretsOutput = & $PY (Join-Path $ROOT "pipeline\fetch_secrets.py") 2>&1
foreach ($line in $secretsOutput) {
  if ($line -match "^(\w+)=(.+)$") { [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2]) }
}
if (Test-Path "$PSScriptRoot\secrets.local.ps1") { . "$PSScriptRoot\secrets.local.ps1" }
if (-not $env:ZOZO_LOGIN_ID) { Write-Output "FATAL: ZOZO credentials empty after secret fetch"; exit 2 }

# First Seller FULL-mode flags
$env:HEADLESS           = "1"
$env:FIRST_SELLER_FULL  = "1"
$env:FIRST_SELLER_LIMIT = "$Limit"

if ($Limit -gt 0) {
  Write-Output ("VALIDATION run: FIRST_SELLER_LIMIT=" + $Limit + " combos. Saves first_seller_LIMIT_test.csv locally; does NOT overwrite GCS.")
  Write-Output "After it looks correct, run the full sweep with:  -Limit 0"
} else {
  Write-Output "FULL run: all patterns (~1,700 searches). This can take a few hours and WILL upload to GCS."
}

Set-Location $ROOT
& $PY (Join-Path $ROOT "pipeline\scrapers\fetch_first_seller.py")
Write-Output ("exit code: " + $LASTEXITCODE)
