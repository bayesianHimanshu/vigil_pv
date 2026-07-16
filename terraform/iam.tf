###############################################################################
# Service accounts + least-privilege IAM + Cloud Audit Logs.
#
#   vigil-pipeline  - runs the batch pipeline / loader / DDL (Phase 0-4) and the
#                     local-to-cloud data path. Read+write on the dataset.
#   vigil-agent     - the Vertex AI Agent Engine runtime identity (orchestrator +
#                     signal agent). Appends agent output, reads views, runs
#                     Gemini, reads the grounding corpus.
###############################################################################

resource "google_service_account" "pipeline" {
  account_id   = "vigil-pipeline"
  display_name = "VIGIL pipeline / loader (batch Phase 0-4)"
  project      = var.project_id
  depends_on   = [time_sleep.after_apis]
}

resource "google_service_account" "agent" {
  account_id   = "vigil-agent"
  display_name = "VIGIL Agent Engine runtime (orchestrator + signal)"
  project      = var.project_id
  depends_on   = [time_sleep.after_apis]
}

# --- Project-level roles -----------------------------------------------------

locals {
  pipeline_project_roles = [
    "roles/bigquery.jobUser",      # run load + query jobs
    "roles/aiplatform.user",       # Gemini + embeddings
    "roles/datastore.user",        # Firestore workflow state
    "roles/discoveryengine.editor" # manage / populate the grounding data store
  ]

  agent_project_roles = [
    "roles/bigquery.jobUser",
    "roles/aiplatform.user",
    "roles/datastore.user",
    "roles/discoveryengine.viewer",
  ]
}

resource "google_project_iam_member" "pipeline" {
  for_each = toset(local.pipeline_project_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "agent" {
  for_each = toset(local.agent_project_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.agent.email}"
}

# --- Dataset-level data access (append-only writers) --------------------------

resource "google_bigquery_dataset_iam_member" "pipeline_editor" {
  dataset_id = google_bigquery_dataset.pv_vigil.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_bigquery_dataset_iam_member" "agent_editor" {
  dataset_id = google_bigquery_dataset.pv_vigil.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.agent.email}"
}

# --- Bucket-level access -----------------------------------------------------

resource "google_storage_bucket_iam_member" "pipeline_raw" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_storage_bucket_iam_member" "pipeline_staging" {
  bucket = google_storage_bucket.staging.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_storage_bucket_iam_member" "agent_staging" {
  bucket = google_storage_bucket.staging.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.agent.email}"
}

resource "google_storage_bucket_iam_member" "agent_raw" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.agent.email}"
}

###############################################################################
# Cloud Audit Logs - Data Access logging on the data-bearing services.
# ADMIN_READ + DATA_READ + DATA_WRITE give the full trail the architecture
# relies on alongside the append-only BigQuery tables.
###############################################################################

resource "google_project_iam_audit_config" "data_access" {
  for_each = toset(var.audit_log_services)
  project  = var.project_id
  service  = each.value

  audit_log_config {
    log_type = "ADMIN_READ"
  }
  audit_log_config {
    log_type = "DATA_READ"
  }
  audit_log_config {
    log_type = "DATA_WRITE"
  }
}
