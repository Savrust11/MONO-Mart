terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {
    bucket = "YOUR_PROJECT_ID-tf-state"
    prefix = "order-system/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "asia-northeast1"  # Tokyo
}

variable "environment" {
  description = "Environment: dev / prod"
  type        = string
  default     = "prod"
}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudtasks.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# Service account for ETL pipeline
resource "google_service_account" "etl_sa" {
  account_id   = "etl-pipeline-sa"
  display_name = "ETL Pipeline Service Account"
}

resource "google_project_iam_member" "etl_sa_roles" {
  for_each = toset([
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/storage.objectAdmin",
    "roles/secretmanager.secretAccessor",
    "roles/cloudtasks.enqueuer",
    "roles/monitoring.metricWriter",
    "roles/logging.logWriter",
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.etl_sa.email}"
}

# Service account for dashboard
resource "google_service_account" "dashboard_sa" {
  account_id   = "dashboard-sa"
  display_name = "Dashboard Service Account"
}

resource "google_project_iam_member" "dashboard_sa_roles" {
  for_each = toset([
    "roles/bigquery.dataViewer",
    "roles/bigquery.jobUser",
    "roles/storage.objectViewer",
    "roles/secretmanager.secretAccessor",
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.dashboard_sa.email}"
}

# Artifact Registry for Docker images
resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = "order-system"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

output "etl_sa_email" {
  value = google_service_account.etl_sa.email
}

output "dashboard_sa_email" {
  value = google_service_account.dashboard_sa.email
}

output "artifact_registry_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/order-system"
}
