locals {
  image_base = "${var.region}-docker.pkg.dev/${var.project_id}/order-system"
}

# ETL Pipeline Cloud Run Job (triggered by Cloud Scheduler)
resource "google_cloud_run_v2_job" "etl_pipeline" {
  name     = "etl-pipeline"
  location = var.region

  template {
    template {
      service_account = google_service_account.etl_sa.email
      max_retries     = 2
      timeout         = "3600s"  # 1 hour max

      containers {
        image = "${local.image_base}/etl-pipeline:latest"

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }

        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "GCS_RAW_BUCKET"
          value = "${var.project_id}-raw-data"
        }
        env {
          name  = "GCS_INPUTS_BUCKET"
          value = "${var.project_id}-inputs"
        }
        env {
          name  = "GCS_EXPORTS_BUCKET"
          value = "${var.project_id}-exports"
        }
        env {
          name  = "BQ_DATASET_RAW"
          value = "raw_layer"
        }
        env {
          name  = "BQ_DATASET_ANALYTICS"
          value = "analytics_layer"
        }
        env {
          name  = "BQ_DATASET_MART"
          value = "mart_layer"
        }
        env {
          name  = "BQ_DATASET_MONITORING"
          value = "monitoring"
        }
        env {
          name  = "TARGET_COVERAGE_WEEKS"
          value = "8"
        }
        env {
          name  = "TZ"
          value = "Asia/Tokyo"
        }
      }
    }
  }

  depends_on = [google_artifact_registry_repository.repo]
}

# Excel Export API — Cloud Run Service (HTTP)
resource "google_cloud_run_v2_service" "excel_export_api" {
  name     = "excel-export-api"
  location = var.region

  template {
    service_account = google_service_account.etl_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = "${local.image_base}/excel-export:latest"

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        cpu_idle = true
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCS_EXPORTS_BUCKET"
        value = "${var.project_id}-exports"
      }
      env {
        name  = "BQ_DATASET_MART"
        value = "mart_layer"
      }
    }
  }

  depends_on = [google_artifact_registry_repository.repo]
}

# Dashboard API — Cloud Run Service (HTTP)
resource "google_cloud_run_v2_service" "dashboard_api" {
  name     = "dashboard-api"
  location = var.region

  template {
    service_account = google_service_account.dashboard_sa.email

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }

    containers {
      image = "${local.image_base}/dashboard:latest"

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = false
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "BQ_DATASET_MART"
        value = "mart_layer"
      }
      env {
        name  = "EXCEL_EXPORT_URL"
        value = google_cloud_run_v2_service.excel_export_api.uri
      }
    }
  }

  depends_on = [google_artifact_registry_repository.repo]
}

# Allow unauthenticated access to dashboard (add Cloud IAP in production for auth)
resource "google_cloud_run_service_iam_member" "dashboard_public" {
  location = google_cloud_run_v2_service.dashboard_api.location
  service  = google_cloud_run_v2_service.dashboard_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "dashboard_url" {
  value = google_cloud_run_v2_service.dashboard_api.uri
}

output "excel_export_url" {
  value = google_cloud_run_v2_service.excel_export_api.uri
}
