# Phase 1 Execution Guide

> Project: MONO-MART 商品発注判断支援システム
> GCP Project: `careful-record-491804-h6`
> Last verified: 2026-05-08

---

## 1. Phase 1 Status Summary

### Implementation Complete

| Layer | Status | Notes |
|-------|--------|-------|
| **Extractors (14 sources)** | ✅ All passing local tests | See `pipeline/tests/test_extractors_local.py` |
| **BigQuery Schemas** | ✅ Raw/Analytics/Mart/Monitoring | 3 new tables added (zozoad_daily, sale_settings, coupon_exclusion) |
| **Pipeline orchestration** | ✅ main.py — both API and CSV ingestion modes | 12-step CSV pipeline |
| **Data validation** | ✅ DataValidator with quality reporting | 5 validators |
| **Monitoring** | ✅ BigQuery audit + Slack alerts | PipelineMonitor |
| **Infrastructure** | ✅ Terraform config ready | `infra/` |
| **Dashboard** | ✅ Next.js skeleton | `dashboard/` |
| **Excel export** | ✅ Flask + signed URLs | `exports/` |

### Local Test Results (2026-05-08)

```
[OK] No.1 受注 (zozo_order_data.csv):       2,570,832 rows
[OK] No.3 予約管理一覧:                            436 rows
[OK] No.4 倉庫在庫 SKU毎 (S20260505.csv):      170,654 rows
[OK] No.6 在庫分析 (20260505.csv):              23,284 rows
[OK] No.7 ZOZOAD (Detail.csv):                   7,776 rows
[OK] No.8 商品別実績(新) (商品別実績_*.csv):     5,717 rows
[OK] No.9 商品マスタ (goods_cs.csv):           42,721 rows
[OK] No.10 原価 (評価額一覧-MMS.csv):           10,790 rows
[OK] No.13 発注明細:                             7,673 rows
[OK] Tableau 予約管理:                           8,024 rows
[OK] No.17 セール設定 (salegoods.csv):           1,921 rows
[OK] No.18 クーポン除外 (3 brands):              8,797 rows
[OK] No.49 着荷データ (MMS):                     1,015 rows
[OK] No.12 sitateru (sitateru_sku.csv):          8,134 rows
─────────────────────────────────────────────────────────
TOTAL:                                       2,866,272 rows verified
```

### Pending (Awaiting Client Action)

| No. | Item | Status | Action |
|-----|------|--------|--------|
| 2 | 発送 (Shipments) | ❌ Not yet downloaded | Client downloads from ZOZOBO 分析＞注文＞発送 |
| 5 | 倉庫在庫 入荷日毎 | ⚠️ Same parser as No.4, just different filter | Client downloads with 入荷日毎 option |
| 11 | PF手数料 (Sheets) | ✅ URL received | Need to extend sheets_extractor for this spreadsheet |
| 12 | sitateru (new format) | ⚠️ Needs new parser | Filter criteria pending in next MTG |
| 14 | 予約管理表 (Sheets) | ✅ URL received | Need to extend sheets_extractor with 2 sheet IDs |

---

## 2. Local Verification Procedure

### Prerequisites

```powershell
# Python 3.14 (already installed via py launcher)
py --version
```

### Run Local Tests

```powershell
cd c:\Users\Administrator\Downloads\Pictures\system\pipeline
$env:PYTHONIOENCODING = "utf-8"
py tests/test_extractors_local.py
```

Expected output: `ALL EXTRACTORS PASSED`

### Run a Single Extractor Manually

```powershell
cd c:\Users\Administrator\Downloads\Pictures\system\pipeline
$env:PYTHONIOENCODING = "utf-8"
py -c "
import sys
sys.path.insert(0, '.')
from extractors.zozo_csv_extractor import ZOZOCsvExtractor
z = ZOZOCsvExtractor()
with open('../data/Detail.csv', 'rb') as f:
    rows = z.parse_zozoad(f.read(), '2026-05-05')
print(f'Parsed {len(rows)} ZOZOAD rows')
print('Sample:', rows[0] if rows else 'empty')
"
```

---

## 3. GCP Deployment Procedure

### Step 1: Install gcloud CLI

```powershell
$installer = "$env:TEMP\GoogleCloudSDKInstaller.exe"
Invoke-WebRequest -Uri "https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe" -OutFile $installer
Start-Process -FilePath $installer -Wait
# After install, RESTART POWERSHELL
```

### Step 2: Authenticate

```powershell
gcloud --version
gcloud auth login            # Login as yujin-yamaguchi@mono-mart.jp
gcloud config set project careful-record-491804-h6
gcloud auth application-default login
```

### Step 3: Verify Project Access

```powershell
gcloud projects describe careful-record-491804-h6
gcloud projects get-iam-policy careful-record-491804-h6 `
    --flatten="bindings[].members" `
    --filter="bindings.members:yujin-yamaguchi@mono-mart.jp" `
    --format="value(bindings.role)"
# Expected: roles/editor
```

### Step 4: Enable Required APIs

```powershell
gcloud services enable bigquery.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable cloudtasks.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com
```

### Step 5: Apply Terraform Infrastructure

```powershell
cd c:\Users\Administrator\Downloads\Pictures\system\infra

# Initialize backend
terraform init

# Update terraform.tfvars
@'
project_id    = "careful-record-491804-h6"
region        = "asia-northeast1"
location      = "asia-northeast1"
gcs_raw_bucket     = "careful-record-491804-h6-raw-data"
gcs_inputs_bucket  = "careful-record-491804-h6-inputs"
gcs_exports_bucket = "careful-record-491804-h6-exports"
'@ | Out-File -Encoding utf8 terraform.tfvars

terraform plan -out=phase1.tfplan
terraform apply phase1.tfplan
```

### Step 6: Create BigQuery Datasets & Tables

```powershell
cd c:\Users\Administrator\Downloads\Pictures\system\pipeline

# Create datasets
bq --location=asia-northeast1 mk --dataset careful-record-491804-h6:raw_layer
bq --location=asia-northeast1 mk --dataset careful-record-491804-h6:analytics_layer
bq --location=asia-northeast1 mk --dataset careful-record-491804-h6:mart_layer
bq --location=asia-northeast1 mk --dataset careful-record-491804-h6:monitoring

# Create tables from schema files
bq query --project_id=careful-record-491804-h6 --use_legacy_sql=false `
    --location=asia-northeast1 < sql/schema/01_raw_layer.sql
bq query --project_id=careful-record-491804-h6 --use_legacy_sql=false `
    --location=asia-northeast1 < sql/schema/02_analytics_layer.sql
bq query --project_id=careful-record-491804-h6 --use_legacy_sql=false `
    --location=asia-northeast1 < sql/schema/03_mart_layer.sql
bq query --project_id=careful-record-491804-h6 --use_legacy_sql=false `
    --location=asia-northeast1 < sql/schema/04_monitoring.sql
```

### Step 7: Populate Secrets

```powershell
# Get the GCP service account JSON for Sheets access (download from GCP Console)
# Then upload secrets:
gcloud secrets create GOOGLE_SA_JSON --data-file=path\to\sa.json
gcloud secrets create SHEETS_SPREADSHEET_ID --replication-policy=automatic
echo -n "1x8frf-cK8nrC6JYB2gZs9emjat0prNpH5x6Zqqb55jg" | `
    gcloud secrets versions add SHEETS_SPREADSHEET_ID --data-file=-

# ZOZO API key (when received)
echo -n "<your-zozo-api-key>" | gcloud secrets create ZOZO_API_KEY --data-file=-

# Optional: Slack webhook
echo -n "<your-slack-webhook>" | gcloud secrets create SLACK_WEBHOOK_URL --data-file=-
```

### Step 8: Upload Sample Data to GCS

```powershell
$BUCKET = "careful-record-491804-h6-raw-data"
$DATE   = "2026-05-05"
$ROOT   = "c:\Users\Administrator\Downloads\Pictures\system"

# Upload one of each file type
gcloud storage cp "$ROOT\zozo_order_data.csv"        gs://$BUCKET/uploads/zozo/orders/$DATE/2026_05_05.csv
gcloud storage cp "$ROOT\S20260505.csv"              gs://$BUCKET/uploads/zozo/inventory_sku/$DATE/s20260505.csv
gcloud storage cp "$ROOT\20260505.csv"               gs://$BUCKET/uploads/zozo/stock_analysis/$DATE/20260505.csv
gcloud storage cp "$ROOT\20260505_ReserveList.csv"   gs://$BUCKET/uploads/zozo/reservations/$DATE/20260505_ReserveList.csv
gcloud storage cp "$ROOT\goods_cs.csv"               gs://$BUCKET/uploads/zozo/product_master/$DATE/goods_cs.csv
gcloud storage cp "$ROOT\評価額一覧-MMS.csv"          gs://$BUCKET/uploads/mms/cost/$DATE/評価額一覧-MMS.csv
gcloud storage cp "$ROOT\発注明細.csv"                gs://$BUCKET/uploads/tableau/hacchu/$DATE/発注明細.csv
gcloud storage cp "$ROOT\予約管理.csv"                gs://$BUCKET/uploads/tableau/yoyaku/$DATE/予約管理.csv
gcloud storage cp "$ROOT\mms_order_data.20260429185608.csv" `
                                                     gs://$BUCKET/uploads/mms/incoming/$DATE/mms_order_data.csv
gcloud storage cp "$ROOT\sitateru_sku.csv"           gs://$BUCKET/uploads/sitateru/sku/$DATE/sitateru_sku.csv

# New data sources
gcloud storage cp "$ROOT\data\Detail.csv"            gs://$BUCKET/uploads/zozo/zozoad/$DATE/Detail.csv
gcloud storage cp "$ROOT\data\商品別実績_20260505.csv" gs://$BUCKET/uploads/zozo/performance/$DATE/商品別実績_20260505.csv
gcloud storage cp "$ROOT\data\salegoods.csv"         gs://$BUCKET/uploads/zozo/sale/$DATE/salegoods.csv
gcloud storage cp "$ROOT\data\MONO-MART_20260506.csv"    gs://$BUCKET/uploads/zozo/coupon/$DATE/MONO-MART_20260506.csv
gcloud storage cp "$ROOT\data\EMMA CLOTHES_20260506.csv" gs://$BUCKET/uploads/zozo/coupon/$DATE/"EMMA CLOTHES_20260506.csv"
gcloud storage cp "$ROOT\data\Chaco closet_20260506.csv" gs://$BUCKET/uploads/zozo/coupon/$DATE/"Chaco closet_20260506.csv"
```

### Step 9: Run Pipeline (CSV Ingestion Mode)

**Option A — Run locally with GCP credentials**

```powershell
cd c:\Users\Administrator\Downloads\Pictures\system\pipeline

# Set environment variables
$env:GCP_PROJECT_ID         = "careful-record-491804-h6"
$env:GCS_RAW_BUCKET         = "careful-record-491804-h6-raw-data"
$env:GCS_INPUTS_BUCKET      = "careful-record-491804-h6-inputs"
$env:GCS_EXPORTS_BUCKET     = "careful-record-491804-h6-exports"
$env:BQ_DATASET_RAW         = "raw_layer"
$env:BQ_DATASET_ANALYTICS   = "analytics_layer"
$env:BQ_DATASET_MART        = "mart_layer"
$env:BQ_DATASET_MONITORING  = "monitoring"
$env:TZ                     = "Asia/Tokyo"

# Install dependencies
py -m pip install -r requirements.txt

# Run pipeline
py main.py --csv-ingest --date 2026-05-05
```

**Option B — Build and deploy as Cloud Run Job**

```powershell
cd c:\Users\Administrator\Downloads\Pictures\system\pipeline

# Build container
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/careful-record-491804-h6/pipeline/etl:v1

# Deploy as Cloud Run Job
gcloud run jobs create pipeline-etl `
    --image=asia-northeast1-docker.pkg.dev/careful-record-491804-h6/pipeline/etl:v1 `
    --region=asia-northeast1 `
    --task-timeout=3600 `
    --memory=2Gi `
    --set-env-vars="GCP_PROJECT_ID=careful-record-491804-h6,GCS_RAW_BUCKET=careful-record-491804-h6-raw-data,BQ_DATASET_RAW=raw_layer,BQ_DATASET_ANALYTICS=analytics_layer,BQ_DATASET_MART=mart_layer,BQ_DATASET_MONITORING=monitoring,TZ=Asia/Tokyo"

# Run the job manually
gcloud run jobs execute pipeline-etl --region=asia-northeast1
```

### Step 10: Verify Data in BigQuery

```sql
-- Run in BigQuery Console: https://console.cloud.google.com/bigquery?project=careful-record-491804-h6

-- 1. Check all raw tables populated
SELECT 'zozo_sales_raw' AS tbl, COUNT(*) AS rows FROM `careful-record-491804-h6.raw_layer.zozo_sales_raw`
UNION ALL SELECT 'zozo_inventory_raw', COUNT(*) FROM `careful-record-491804-h6.raw_layer.zozo_inventory_raw`;

-- 2. Check analytics layer counts
SELECT 'sales_daily' AS tbl, COUNT(*) AS rows FROM `careful-record-491804-h6.analytics_layer.sales_daily`
UNION ALL SELECT 'inventory_snapshot', COUNT(*) FROM `careful-record-491804-h6.analytics_layer.inventory_snapshot`
UNION ALL SELECT 'product_master', COUNT(*) FROM `careful-record-491804-h6.analytics_layer.product_master`
UNION ALL SELECT 'reservations', COUNT(*) FROM `careful-record-491804-h6.analytics_layer.reservations`
UNION ALL SELECT 'cost_master', COUNT(*) FROM `careful-record-491804-h6.analytics_layer.cost_master`
UNION ALL SELECT 'stock_analysis', COUNT(*) FROM `careful-record-491804-h6.analytics_layer.stock_analysis`
UNION ALL SELECT 'incoming_stock', COUNT(*) FROM `careful-record-491804-h6.analytics_layer.incoming_stock`
UNION ALL SELECT 'zozoad_daily', COUNT(*) FROM `careful-record-491804-h6.analytics_layer.zozoad_daily`
UNION ALL SELECT 'sale_settings', COUNT(*) FROM `careful-record-491804-h6.analytics_layer.sale_settings`
UNION ALL SELECT 'coupon_exclusion', COUNT(*) FROM `careful-record-491804-h6.analytics_layer.coupon_exclusion`
ORDER BY tbl;

-- 3. Check mart layer
SELECT urgency_level, COUNT(*) AS sku_count
FROM `careful-record-491804-h6.mart_layer.order_analysis`
WHERE analysis_date = '2026-05-05'
GROUP BY urgency_level
ORDER BY urgency_level;

-- 4. Check pipeline run logs
SELECT run_id, step_name, status, rows_processed, started_at, completed_at
FROM `careful-record-491804-h6.monitoring.pipeline_runs`
ORDER BY started_at DESC
LIMIT 20;
```

### Step 11: Schedule Daily Run

```powershell
# Cloud Scheduler — daily at 07:00 JST as per meeting decision
gcloud scheduler jobs create http pipeline-daily `
    --location=asia-northeast1 `
    --schedule="0 7 * * *" `
    --time-zone="Asia/Tokyo" `
    --uri="https://asia-northeast1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/careful-record-491804-h6/jobs/pipeline-etl:run" `
    --http-method=POST `
    --oauth-service-account-email=pipeline-runner@careful-record-491804-h6.iam.gserviceaccount.com
```

---

## 4. Test Procedure

### Test 1: Unit Tests (Local)

**Expected:** All 14 extractors parse sample files successfully.

```powershell
cd c:\Users\Administrator\Downloads\Pictures\system\pipeline
$env:PYTHONIOENCODING = "utf-8"
py tests/test_extractors_local.py
```

**Pass criteria:** Output ends with `ALL EXTRACTORS PASSED`.

### Test 2: GCS Upload Verification

```powershell
gcloud storage ls gs://careful-record-491804-h6-raw-data/uploads/zozo/orders/2026-05-05/
gcloud storage ls gs://careful-record-491804-h6-raw-data/uploads/zozo/zozoad/2026-05-05/
```

**Pass criteria:** Files listed with non-zero sizes.

### Test 3: BigQuery Schema Creation

```powershell
bq ls --project_id=careful-record-491804-h6 raw_layer
bq ls --project_id=careful-record-491804-h6 analytics_layer
bq ls --project_id=careful-record-491804-h6 mart_layer
```

**Pass criteria:** All tables listed (4 raw, 10 analytics, 2 mart).

### Test 4: End-to-End Pipeline Run

```powershell
cd pipeline
py main.py --csv-ingest --date 2026-05-05
```

**Pass criteria:**
- Exit code 0
- Console shows `CSV ingestion complete` with all 12 steps `status: ok`
- BigQuery tables contain data (run Step 10 verification queries)

### Test 5: KPI Mart Calculation

After Test 4, query the mart table:

```sql
SELECT urgency_level, COUNT(*) AS sku_count, AVG(stock_days_7d) AS avg_stock_days
FROM `careful-record-491804-h6.mart_layer.order_analysis`
WHERE analysis_date = '2026-05-05'
GROUP BY urgency_level;
```

**Pass criteria:**
- All 4 urgency levels present (CRITICAL, WARNING, OK, OVERSTOCK)
- Total row count > 10,000 (matches inventory volume)
- avg_stock_days values are reasonable (0–365)

### Test 6: Spot-Check Specific Product

Pick a known product and verify the calculation:

```sql
SELECT
  sku_code, product_name, color_name, size,
  stock_quantity, free_inventory, sales_7d, sales_30d,
  stock_days_7d, trend_coefficient, recommended_order_qty, urgency_level
FROM `careful-record-491804-h6.mart_layer.order_analysis`
WHERE analysis_date = '2026-05-05'
  AND product_code = 'sc1439'  -- pick a real product
LIMIT 10;
```

**Pass criteria:** Numbers align with manual calculation from raw data.

### Test 7: Dashboard Connectivity

```powershell
cd c:\Users\Administrator\Downloads\Pictures\system\dashboard
$env:GCP_PROJECT_ID = "careful-record-491804-h6"
npm install
npm run dev
# Open http://localhost:3000/dashboard
```

**Pass criteria:**
- Dashboard loads
- Product list displays SKUs from BigQuery
- Urgency filter works (CRITICAL/WARNING/OK/OVERSTOCK)
- Brand filter shows 7+ brands

### Test 8: Excel Export

```powershell
cd c:\Users\Administrator\Downloads\Pictures\system\exports
py -m pip install -r requirements.txt
$env:GCP_PROJECT_ID = "careful-record-491804-h6"
$env:GCS_EXPORTS_BUCKET = "careful-record-491804-h6-exports"
flask run --port 5001
```

In another terminal:
```powershell
Invoke-RestMethod -Uri "http://localhost:5001/generate" `
    -Method POST -ContentType "application/json" `
    -Body '{"date":"2026-05-05"}'
```

**Pass criteria:**
- Returns JSON with `download_url`
- URL is downloadable, returns valid .xlsx
- Excel layout matches `分析表イメージ.pdf` template

---

## 5. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `PERMISSION_DENIED` on BigQuery | Editor role not active | Wait 2–5 min, or re-grant |
| `UnicodeDecodeError` on CSV | Wrong encoding | All CSVs are cp932 except 商品別実績 (UTF-8) |
| `0 rows parsed` | Column name mismatch | Check headers with `head -1 file.csv` |
| `bq: command not found` | gcloud SDK not in PATH | Restart PowerShell after install |
| Cloud Run Job times out | Default 60min limit | Increase via `--task-timeout=3600` |
| Slack alerts not firing | Webhook secret missing | Verify `SLACK_WEBHOOK_URL` in Secret Manager |
| Dashboard shows no data | BQ project mismatch | Set `GCP_PROJECT_ID` env var to `careful-record-491804-h6` |

---

## 6. Daily Operations Runbook

### Morning Check (after 07:30 JST)

```sql
-- Verify yesterday's pipeline succeeded
SELECT step_name, status, rows_processed, completed_at
FROM `careful-record-491804-h6.monitoring.pipeline_runs`
WHERE run_date = CURRENT_DATE("Asia/Tokyo") - 1
ORDER BY started_at DESC;
```

If any step shows `FAILED`:
1. Check Slack for alert details
2. View Cloud Run Job logs: `gcloud run jobs executions describe ... --region=asia-northeast1`
3. Re-run for that date: `gcloud run jobs execute pipeline-etl --region=asia-northeast1 --args="--date,2026-05-07"`

### Manual CSV Re-ingestion

If a specific data source needs to be reprocessed (e.g., client uploads corrected data):

```powershell
# Upload corrected file
gcloud storage cp corrected_file.csv gs://careful-record-491804-h6-raw-data/uploads/zozo/orders/2026-05-05/

# Re-run pipeline for that date
py main.py --csv-ingest --date 2026-05-05
```

The pipeline is idempotent — re-running the same date overwrites the partition.

---

## 7. Phase 1 Completion Checklist

```
[x] Pipeline code: 14 extractors implemented & tested locally
[x] BigQuery schema: 4 raw + 10 analytics + 2 mart tables defined
[x] Pipeline orchestration: 12-step CSV ingestion mode
[x] Local tests passing: ALL EXTRACTORS PASSED
[ ] gcloud CLI installed and authenticated (your action)
[ ] Terraform applied to careful-record-491804-h6 (after auth)
[ ] BigQuery datasets/tables created (after Terraform)
[ ] Secrets uploaded to Secret Manager (after auth)
[ ] Sample data uploaded to GCS (after Terraform)
[ ] First end-to-end pipeline run successful (after upload)
[ ] KPI mart populated with valid data (after pipeline run)
[ ] Cloud Scheduler configured for 07:00 JST daily (after pipeline run)
[ ] Dashboard connected to BigQuery (after mart populated)
[ ] Excel export working (after dashboard)
[ ] KPI formulas verified by client (separate review meeting)
```

Steps 1–4 ✅ are done. Steps 5+ require GCP credentials in your local environment.
