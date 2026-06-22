# BigQuery datasets — 3-layer medallion architecture
resource "google_bigquery_dataset" "raw_layer" {
  dataset_id                  = "raw_layer"
  friendly_name               = "Raw Layer"
  description                 = "Append-only raw ingestion from all sources. Never updated, only appended."
  location                    = var.region
  default_table_expiration_ms = null

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }
  access {
    role          = "WRITER"
    user_by_email = google_service_account.etl_sa.email
  }
}

resource "google_bigquery_dataset" "analytics_layer" {
  dataset_id    = "analytics_layer"
  friendly_name = "Analytics Layer"
  description   = "Cleaned, typed, deduplicated data. Source of truth for all KPI calculations."
  location      = var.region

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }
  access {
    role          = "WRITER"
    user_by_email = google_service_account.etl_sa.email
  }
  access {
    role          = "READER"
    user_by_email = google_service_account.dashboard_sa.email
  }
}

resource "google_bigquery_dataset" "mart_layer" {
  dataset_id    = "mart_layer"
  friendly_name = "Mart Layer"
  description   = "Aggregated KPI tables consumed by the dashboard and Excel export."
  location      = var.region

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }
  access {
    role          = "WRITER"
    user_by_email = google_service_account.etl_sa.email
  }
  access {
    role          = "READER"
    user_by_email = google_service_account.dashboard_sa.email
  }
}

resource "google_bigquery_dataset" "monitoring" {
  dataset_id    = "monitoring"
  friendly_name = "Pipeline Monitoring"
  description   = "Pipeline run logs, error tracking, data quality metrics."
  location      = var.region

  access {
    role          = "OWNER"
    special_group = "projectOwners"
  }
  access {
    role          = "WRITER"
    user_by_email = google_service_account.etl_sa.email
  }
}
