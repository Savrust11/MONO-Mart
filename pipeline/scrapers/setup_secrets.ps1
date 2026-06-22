# ZOZO scraper credentials → Secret Manager
#
# Run once to register the ZOZO login credentials in GCP Secret Manager.
# DO NOT commit this file with credentials filled in.

$ErrorActionPreference = "Stop"
$PROJECT = "mono-back-office-system"

Write-Host "Registering ZOZO credentials to Secret Manager..." -ForegroundColor Cyan

# Edit these inline OR set as env vars before running this script:
$ZOZO_LOGIN_ID       = if ($env:ZOZO_LOGIN_ID)       { $env:ZOZO_LOGIN_ID }       else { Read-Host "ZOZO_LOGIN_ID" }
$ZOZO_LOGIN_PASSWORD = if ($env:ZOZO_LOGIN_PASSWORD) { $env:ZOZO_LOGIN_PASSWORD } else { Read-Host "ZOZO_LOGIN_PASSWORD" -AsSecureString | ConvertFrom-SecureString -AsPlainText }
$ZOZO_TENANT         = if ($env:ZOZO_TENANT)         { $env:ZOZO_TENANT }         else { "MONO-MART" }

function Set-GcpSecret {
    param([string]$Name, [string]$Value)
    # Check existence
    $exists = (gcloud secrets describe $Name --project=$PROJECT 2>$null) -ne $null
    if (-not $exists) {
        Write-Host "  Creating secret $Name..." -ForegroundColor Yellow
        $Value | gcloud secrets create $Name --project=$PROJECT --data-file=- --replication-policy=automatic
    } else {
        Write-Host "  Adding new version to $Name..." -ForegroundColor Yellow
        $Value | gcloud secrets versions add $Name --project=$PROJECT --data-file=-
    }
}

Set-GcpSecret -Name "ZOZO_LOGIN_ID"       -Value $ZOZO_LOGIN_ID
Set-GcpSecret -Name "ZOZO_LOGIN_PASSWORD" -Value $ZOZO_LOGIN_PASSWORD
Set-GcpSecret -Name "ZOZO_TENANT"         -Value $ZOZO_TENANT

Write-Host "`nDone. Secrets registered in project $PROJECT" -ForegroundColor Green
Write-Host "Verify with: gcloud secrets list --project=$PROJECT"
