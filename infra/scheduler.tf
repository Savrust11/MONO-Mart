# Cloud Scheduler — triggers ETL pipeline nightly at 02:00 JST
resource "google_cloud_scheduler_job" "nightly_etl" {
  name             = "nightly-etl-pipeline"
  description      = "Trigger ETL pipeline nightly at 02:00 JST to process previous day's data"
  schedule         = "0 2 * * *"  # 02:00 JST = 17:00 UTC previous day
  time_zone        = "Asia/Tokyo"
  attempt_deadline = "3600s"

  retry_config {
    retry_count          = 3
    min_backoff_duration = "300s"   # 5 min between retries
    max_backoff_duration = "3600s"  # 1 hour max backoff
  }

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/etl-pipeline:run"

    oauth_token {
      service_account_email = google_service_account.etl_sa.email
    }
  }

  depends_on = [
    google_cloud_run_v2_job.etl_pipeline,
    google_project_service.apis,
  ]
}

# Cloud Tasks queue for async Excel generation
resource "google_cloud_tasks_queue" "excel_export" {
  name     = "excel-export-queue"
  location = var.region

  rate_limits {
    max_concurrent_dispatches = 5
    max_dispatches_per_second = 2
  }

  retry_config {
    max_attempts  = 3
    min_backoff   = "10s"
    max_backoff   = "300s"
    max_doublings = 4
  }
}
