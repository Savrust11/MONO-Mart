# =============================================================================
# One-time: run the First Seller form discovery with the SAME environment that
# run_daily.ps1 uses (Python path, GCP creds, Secret Manager, ZOZO override).
# Produces seller_form_dump.txt in the repo root.
#   powershell -ExecutionPolicy Bypass -File run_discover.ps1
# NOTE: ASCII-only on purpose (Windows PowerShell 5.1 mis-parses non-ASCII .ps1).
# =============================================================================
$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\Administrator\Downloads\system"
$PY   = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"
$PROJ = "mono-back-office-system"

$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONIOENCODING = "utf-8"

# GCP Application Default Credentials (for Secret Manager / BigQuery clients)
$adc   = Join-Path $env:APPDATA "gcloud\application_default_credentials.json"
$saKey = Join-Path $ROOT "pipeline\sheets-sa-key.json"
if (Test-Path $adc)       { $env:GOOGLE_APPLICATION_CREDENTIALS = $adc }
elseif (Test-Path $saKey) { $env:GOOGLE_APPLICATION_CREDENTIALS = $saKey }
$env:GOOGLE_CLOUD_PROJECT = $PROJ

# Credentials from Secret Manager (ZOZO / MMS etc.)
$secretsOutput = & $PY (Join-Path $ROOT "pipeline\fetch_secrets.py") 2>&1
foreach ($line in $secretsOutput) {
  if ($line -match "^(\w+)=(.+)$") { [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2]) }
}
# Correct ZOZO login account override (same as run_daily.ps1) from local file
if (Test-Path "$PSScriptRoot\secrets.local.ps1") { . "$PSScriptRoot\secrets.local.ps1" }
if (-not $env:ZOZO_LOGIN_ID) { Write-Output "FATAL: ZOZO credentials empty after secret fetch"; exit 2 }

# Run discovery (writes seller_form_dump.txt to $ROOT)
Set-Location $ROOT
$env:HEADLESS = "1"
& $PY (Join-Path $ROOT "pipeline\scrapers\discover_seller_form.py")
Write-Output ("done. output -> " + (Join-Path $ROOT "seller_form_dump.txt"))
