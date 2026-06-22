# Deploy ZOZO scraper as Cloud Run Job + schedule daily at 06:30 JST
# (runs before the ETL pipeline at 07:00 JST)

$ErrorActionPreference = "Stop"

$PROJECT  = "mono-back-office-system"
$REGION   = "asia-northeast1"
$REPO     = "pipeline"
$IMAGE    = "asia-northeast1-docker.pkg.dev/$PROJECT/$REPO/zozo-scraper:latest"
$JOB_NAME = "zozo-scraper"
$SCHEDULE = "30 6 * * *"
$SA_EMAIL = "pipeline-runner@$PROJECT.iam.gserviceaccount.com"

Write-Host "=== Build & push scraper image ===" -ForegroundColor Cyan
gcloud builds submit `
    --project=$PROJECT `
    --tag=$IMAGE `
    --file=scrapers/Dockerfile.scraper `
    .

Write-Host "`n=== Deploy as Cloud Run Job ===" -ForegroundColor Cyan
gcloud run jobs deploy $JOB_NAME `
    --project=$PROJECT `
    --region=$REGION `
    --image=$IMAGE `
    --service-account=$SA_EMAIL `
    --max-retries=2 `
    --task-timeout=30m `
    --memory=2Gi `
    --cpu=1 `
    --set-env-vars="GCP_PROJECT_ID=$PROJECT,GCS_RAW_BUCKET=$PROJECT-raw-data,TZ=Asia/Tokyo,HEADLESS=1" `
    --set-secrets="ZOZO_LOGIN_ID=ZOZO_LOGIN_ID:latest,ZOZO_LOGIN_PASSWORD=ZOZO_LOGIN_PASSWORD:latest,ZOZO_TENANT=ZOZO_TENANT:latest"

Write-Host "`n=== Schedule daily at $SCHEDULE JST ===" -ForegroundColor Cyan
$EXISTING_SCHEDULER = gcloud scheduler jobs list --location=$REGION --project=$PROJECT --filter="name:zozo-scraper-daily" --format="value(name)" 2>$null
if (-not $EXISTING_SCHEDULER) {
    gcloud scheduler jobs create http zozo-scraper-daily `
        --project=$PROJECT `
        --location=$REGION `
        --schedule=$SCHEDULE `
        --time-zone="Asia/Tokyo" `
        --uri="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT/jobs/${JOB_NAME}:run" `
        --http-method=POST `
        --oauth-service-account-email=$SA_EMAIL
} else {
    gcloud scheduler jobs update http zozo-scraper-daily `
        --project=$PROJECT `
        --location=$REGION `
        --schedule=$SCHEDULE `
        --time-zone="Asia/Tokyo"
}

Write-Host "`nDeployment complete." -ForegroundColor Green
Write-Host "Test run: gcloud run jobs execute $JOB_NAME --region=$REGION --project=$PROJECT"
