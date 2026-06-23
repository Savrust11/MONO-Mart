# =============================================================================
# Backfill / re-import ZOZO source data into BigQuery for specific dates.
#
# IMPORTANT: this is a DAY-LEVEL import. For each date it re-fetches the WHOLE
# day's orders+shipped export from ZOZO (every brand part number) and re-ingests
# it. The loader does DELETE+INSERT by sale_date, so it replaces that day's data
# for EVERY product (idempotent, no duplicates). The customer noticed SC1032, but
# this restores all part numbers on those days, not just SC1032.
#
# After each date it VERIFIES in BigQuery (day-level row count + distinct product
# count) so you can see the whole day actually landed. A final SUMMARY lists
# OK / FAILED per date.
#
#   Default (the 4 dates the customer flagged):
#     powershell -ExecutionPolicy Bypass -File run_recover_dates.ps1
#   Wider May cluster (05-22..05-25 are also empty for SC1032):
#     powershell -ExecutionPolicy Bypass -File run_recover_dates.ps1 -Dates "2026-05-22","2026-05-23","2026-05-24","2026-05-25"
#
# NOTE on 2026-06-21 / 2026-06-22:
#   The auto-fetched orders file for these days produced 0 rows (06-21 came back
#   empty; 06-22's file did not parse). If the re-fetch below VERIFIES as FAILED
#   (0 rows) for them, use the MANUAL-CSV path instead:
#     1) In ZOZO BackOffice, download that day's 受注 CSV.
#     2) Upload it to:
#          gs://mono-back-office-system-raw-data/uploads/zozo/orders/<DATE>/<yyyy_mm_dd>.csv
#     3) Re-run only the ingest for that date:
#          python pipeline\main.py --csv-ingest --date <DATE>
#          python pipeline\scrapers\verify_date_orders.py <DATE>
#
# ASCII-only on purpose (Windows PowerShell 5.1 mis-parses non-ASCII .ps1).
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
$env:GCP_PROJECT_ID = "mono-back-office-system"
$env:GCS_RAW_BUCKET = "mono-back-office-system-raw-data"
$env:HEADLESS = "1"

# Secret Manager creds + ZOZO login override (same as run_daily.ps1)
$secretsOut = & $PY (Join-Path $ROOT "pipeline\fetch_secrets.py") 2>$null
foreach ($line in $secretsOut) { if ($line -match "^(\w+)=(.+)$") { Set-Item -Path "env:$($Matches[1])" -Value $Matches[2] } }
if (Test-Path "$PSScriptRoot\secrets.local.ps1") { . "$PSScriptRoot\secrets.local.ps1" }
if (-not $env:ZOZO_LOGIN_ID) { Log "FATAL: ZOZO credentials empty after secret fetch"; exit 2 }

$results = @()
Log ("===== BACKFILL START (day-level, all part numbers) dates=" + ($Dates -join ",") + " =====")
foreach ($d in $Dates) {
  # [1/3] re-fetch the WHOLE day (orders + shipped, every product) to GCS
  Log "----- $d : [1/3] re-fetch (orders,shipped - full day, all products) -----"
  $env:TARGET_DATE = $d
  $env:ONLY = "orders,shipped"
  & $PY (Join-Path $ROOT "pipeline\scrapers\zozo_scraper.py") 2>&1 | ForEach-Object { Log $_ }
  $fetchExit = $LASTEXITCODE

  # [2/3] re-ingest -> BigQuery (loader DELETE+INSERT by sale_date; all products)
  Log "----- $d : [2/3] re-ingest (DELETE+INSERT by sale_date) -----"
  & $PY (Join-Path $ROOT "pipeline\main.py") "--csv-ingest" "--date" $d 2>&1 | ForEach-Object { Log $_ }
  $ingestExit = $LASTEXITCODE

  # [3/3] verify in BigQuery that the WHOLE day has rows now (all part numbers)
  Log "----- $d : [3/3] verify day-level in BigQuery -----"
  $verifyOut = & $PY (Join-Path $ROOT "pipeline\scrapers\verify_date_orders.py") $d "SC1032" 2>&1
  $verifyExit = $LASTEXITCODE
  $verifyOut | ForEach-Object { Log $_ }

  $status = if ($verifyExit -eq 0) { "OK" } else { "FAILED (0 rows -> use MANUAL-CSV path, see header)" }
  Log "----- $d : RESULT = $status  (fetch_exit=$fetchExit ingest_exit=$ingestExit) -----"
  $results += [pscustomobject]@{ Date = $d; Status = $status; Detail = ($verifyOut -join ' ') }
  Start-Sleep -Seconds 5
}

Log "===== BACKFILL SUMMARY ====="
foreach ($r in $results) { Log ("  " + $r.Date + " : " + $r.Status + "  | " + $r.Detail) }
$okCount = ($results | Where-Object { $_.Status -eq "OK" }).Count
Log ("===== DONE: " + $okCount + "/" + $results.Count + " dates loaded into BigQuery =====")
if ($okCount -lt $results.Count) { Log "WARN: some dates still 0 rows -- re-download those days' CSV and use the MANUAL-CSV path in the header." }
