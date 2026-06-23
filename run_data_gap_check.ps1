# =============================================================================
# Data-gap monitor: detect dates whose orders import is MISSING or abnormally LOW
# in BigQuery (the "success but 0 rows" case that failure-alerting misses, e.g.
# 2026-06-21 / 06-22). Records to monitoring.pipeline_runs (shows on dashboard),
# sends a Slack alert if SLACK_WEBHOOK_URL is set, and prints the exact backfill
# command for any bad dates. Exit 1 if gaps found, else 0.
#
#   powershell -ExecutionPolicy Bypass -File run_data_gap_check.ps1
#   powershell -ExecutionPolicy Bypass -File run_data_gap_check.ps1 -Days 60
#
# Schedule this daily (Task Scheduler) AFTER run_daily.ps1, or rely on the call
# already wired into the end of run_daily.ps1.
#
# ASCII-only on purpose (Windows PowerShell 5.1 mis-parses non-ASCII .ps1).
# =============================================================================
param([int]$Days = 35)

$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\Administrator\Downloads\system"
$PY   = "C:\Users\Administrator\AppData\Local\Python\bin\python.exe"

$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
$env:PYTHONIOENCODING = "utf-8"
$env:GOOGLE_APPLICATION_CREDENTIALS = Join-Path $ROOT "pipeline\sheets-sa-key.json"
$env:GOOGLE_CLOUD_PROJECT = "mono-back-office-system"
$env:GCP_PROJECT_ID = "mono-back-office-system"

# Slack webhook (optional) from Secret Manager, same as the daily run.
$secretsOut = & $PY (Join-Path $ROOT "pipeline\fetch_secrets.py") 2>$null
foreach ($line in $secretsOut) { if ($line -match "^(\w+)=(.+)$") { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] } }

Push-Location (Join-Path $ROOT "pipeline")
& $PY (Join-Path $ROOT "pipeline\scrapers\check_data_gaps.py") "--days" $Days
$code = $LASTEXITCODE
Pop-Location
Write-Output ("data_gap_check exit=" + $code + " (1 = gaps found)")
exit $code
