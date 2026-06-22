# Deployment Guide

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI authenticated
- `terraform` >= 1.6
- `docker` + `gcloud auth configure-docker`
- Node.js 20+ (for dashboard)
- Python 3.12+ (for pipeline)

---

## Step 1: GCP Infrastructure

```bash
cd infra/
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set project_id

terraform init
terraform plan
terraform apply
```

---

## Step 2: Upload Secrets to Secret Manager

```bash
PROJECT_ID="your-project-id"

# ZOZO API key
echo -n "YOUR_ZOZO_API_KEY" | \
  gcloud secrets versions add ZOZO_API_KEY --data-file=- --project=$PROJECT_ID

# Google service account JSON (for Sheets access)
gcloud secrets versions add GOOGLE_SA_JSON \
  --data-file=path/to/service-account.json --project=$PROJECT_ID

# Google Sheets spreadsheet ID
echo -n "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms" | \
  gcloud secrets versions add SHEETS_SPREADSHEET_ID --data-file=- --project=$PROJECT_ID

# Slack webhook (optional)
echo -n "https://hooks.slack.com/services/..." | \
  gcloud secrets versions add SLACK_WEBHOOK_URL --data-file=- --project=$PROJECT_ID
```

---

## Step 3: Deploy Python ETL Pipeline

```bash
REGION="asia-northeast1"
PROJECT_ID="your-project-id"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/order-system"

cd pipeline/

docker build -t ${REGISTRY}/etl-pipeline:latest .
docker push ${REGISTRY}/etl-pipeline:latest

gcloud run jobs update etl-pipeline \
  --image ${REGISTRY}/etl-pipeline:latest \
  --region ${REGION} \
  --project ${PROJECT_ID}
```

---

## Step 4: Initialize BigQuery Schema

```bash
PROJECT_ID="your-project-id"

bq query --project_id=$PROJECT_ID < pipeline/sql/schema/01_raw_layer.sql
bq query --project_id=$PROJECT_ID < pipeline/sql/schema/02_analytics_layer.sql
bq query --project_id=$PROJECT_ID < pipeline/sql/schema/03_mart_layer.sql
```

---

## Step 5: Deploy Excel Export Service

```bash
cd exports/

docker build -t ${REGISTRY}/excel-export:latest .
docker push ${REGISTRY}/excel-export:latest

gcloud run services update excel-export-api \
  --image ${REGISTRY}/excel-export:latest \
  --region ${REGION} \
  --project ${PROJECT_ID}
```

---

## Step 6: Deploy Dashboard

```bash
cd dashboard/

docker build -t ${REGISTRY}/dashboard:latest .
docker push ${REGISTRY}/dashboard:latest

gcloud run services update dashboard-api \
  --image ${REGISTRY}/dashboard:latest \
  --region ${REGION} \
  --project ${PROJECT_ID}
```

---

## Step 7: Run Initial Pipeline

```bash
# Trigger the ETL job manually for today
gcloud run jobs execute etl-pipeline \
  --region ${REGION} \
  --project ${PROJECT_ID}

# Or for a specific date:
gcloud run jobs execute etl-pipeline \
  --region ${REGION} \
  --project ${PROJECT_ID} \
  --args="--date,2025-11-03"
```

---

## Step 8: Upload Initial Cost Master Excel

Upload your cost master Excel file to GCS inputs bucket:

```bash
gsutil cp path/to/cost_master.xlsx gs://${PROJECT_ID}-inputs/cost/
```

The pipeline will automatically pick up the latest file on next run.

---

## Nightly Schedule

Cloud Scheduler fires at 02:00 JST every night, processing the previous day's data.
Monitor pipeline runs in BigQuery:

```sql
SELECT * FROM `monitoring.pipeline_runs`
WHERE run_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
ORDER BY started_at DESC;
```
