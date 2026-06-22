# GCS bucket for raw data ingestion
resource "google_storage_bucket" "raw_data" {
  name          = "${var.project_id}-raw-data"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age            = 90
      matches_prefix = ["raw/"]
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age            = 365
      matches_prefix = ["archive/"]
    }
    action {
      type = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
}

# GCS bucket for Excel input files (cost master uploads)
resource "google_storage_bucket" "inputs" {
  name          = "${var.project_id}-inputs"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
}

# GCS bucket for generated Excel exports
resource "google_storage_bucket" "exports" {
  name          = "${var.project_id}-exports"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }
}

# IAM bindings
resource "google_storage_bucket_iam_member" "etl_raw_admin" {
  bucket = google_storage_bucket.raw_data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.etl_sa.email}"
}

resource "google_storage_bucket_iam_member" "etl_inputs_reader" {
  bucket = google_storage_bucket.inputs.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.etl_sa.email}"
}

resource "google_storage_bucket_iam_member" "etl_exports_admin" {
  bucket = google_storage_bucket.exports.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.etl_sa.email}"
}

output "raw_data_bucket" {
  value = google_storage_bucket.raw_data.name
}

output "inputs_bucket" {
  value = google_storage_bucket.inputs.name
}

output "exports_bucket" {
  value = google_storage_bucket.exports.name
}
