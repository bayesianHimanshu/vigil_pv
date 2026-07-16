###############################################################################
# BigQuery - the analytical system of record + audit trail.
#
# The dataset is managed here (location, labels, CMEK). The schema itself
# (9 tables + 8 views) is defined in ../sql/data_model.sql, which is the single
# source of truth, and applied by deploy/deploy.sh via scripts/apply_ddl.py.
# Re-encoding every view's SQL as google_bigquery_table resources would
# duplicate that file and drift; the DDL applier keeps them in lockstep.
###############################################################################

resource "google_bigquery_dataset" "pv_vigil" {
  dataset_id    = var.dataset_id
  project       = var.project_id
  location      = var.bq_location
  friendly_name = "Project VIGIL - pharmacovigilance"
  description   = "Agentic PV on VAERS: raw / reference / ground-truth / agent (append-only) / eval / signal zones."
  labels        = var.labels

  delete_contents_on_destroy = var.bq_delete_contents_on_destroy

  dynamic "default_encryption_configuration" {
    for_each = var.enable_cmek ? [1] : []
    content {
      kms_key_name = google_kms_crypto_key.bq[0].id
    }
  }

  depends_on = [
    time_sleep.after_apis,
    google_kms_crypto_key_iam_member.bq_agent,
  ]
}
