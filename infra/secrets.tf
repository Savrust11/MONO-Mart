# Secret Manager — stores all credentials, never hardcoded
resource "google_secret_manager_secret" "zozo_api_key" {
  secret_id = "ZOZO_API_KEY"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "google_sa_json" {
  secret_id = "GOOGLE_SA_JSON"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "slack_webhook_url" {
  secret_id = "SLACK_WEBHOOK_URL"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "sheets_spreadsheet_id" {
  secret_id = "SHEETS_SPREADSHEET_ID"
  replication {
    auto {}
  }
}

# Grant ETL SA access to all secrets
resource "google_secret_manager_secret_iam_member" "etl_sa_zozo" {
  secret_id = google_secret_manager_secret.zozo_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.etl_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "etl_sa_google_sa" {
  secret_id = google_secret_manager_secret.google_sa_json.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.etl_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "etl_sa_slack" {
  secret_id = google_secret_manager_secret.slack_webhook_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.etl_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "etl_sa_sheets" {
  secret_id = google_secret_manager_secret.sheets_spreadsheet_id.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.etl_sa.email}"
}
