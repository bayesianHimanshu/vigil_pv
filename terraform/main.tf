###############################################################################
# Shared data sources + naming.
###############################################################################

data "google_project" "this" {
  project_id = var.project_id
}

locals {
  project_number = data.google_project.this.number

  raw_bucket_name     = var.raw_bucket_name != "" ? var.raw_bucket_name : "${var.project_id}-vigil-raw"
  staging_bucket_name = var.staging_bucket_name != "" ? var.staging_bucket_name : "${var.project_id}-vigil-agent-staging"
}

# Google-managed service agents that need CMEK access when encryption is on.
data "google_bigquery_default_service_account" "bq" {
  project = var.project_id
}

data "google_storage_project_service_account" "gcs" {
  project = var.project_id
}
