###############################################################################
# Outputs - consumed by deploy/deploy.sh to generate the runtime .env and to
# wire the Agent Engine deploy.
###############################################################################

output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "dataset_id" {
  value       = google_bigquery_dataset.pv_vigil.dataset_id
  description = "BigQuery dataset (VIGIL_DATASET)."
}

output "dataset_location" {
  value = google_bigquery_dataset.pv_vigil.location
}

output "raw_bucket" {
  value       = google_storage_bucket.raw.name
  description = "Raw VAERS landing / lineage bucket (VIGIL_BUCKET)."
}

output "staging_bucket" {
  value       = google_storage_bucket.staging.name
  description = "Vertex AI Agent Engine staging bucket."
}

output "pipeline_service_account" {
  value       = google_service_account.pipeline.email
  description = "Identity for the batch pipeline / loader / DDL."
}

output "agent_service_account" {
  value       = google_service_account.agent.email
  description = "Identity for the Agent Engine runtime (orchestrator + signal)."
}

output "firestore_database" {
  value = google_firestore_database.default.name
}

output "bq_kms_key" {
  value       = var.enable_cmek ? google_kms_crypto_key.bq[0].id : null
  description = "CMEK key protecting BigQuery (null if CMEK disabled)."
}

output "gcs_kms_key" {
  value       = var.enable_cmek ? google_kms_crypto_key.gcs[0].id : null
  description = "CMEK key protecting Cloud Storage (null if CMEK disabled)."
}

output "vertex_ai_search_data_store" {
  value       = var.enable_vertex_ai_search ? google_discovery_engine_data_store.meddra[0].name : null
  description = "Discovery Engine data store resource name (null if disabled)."
}

# A ready-to-source environment block for the application (mirrors .env).
output "runtime_env" {
  description = "Copy into .env (or let deploy.sh write it)."
  value       = <<-EOT
    export VIGIL_PROJECT=${var.project_id}
    export VIGIL_LOCATION=${var.region}
    export VIGIL_DATASET=${google_bigquery_dataset.pv_vigil.dataset_id}
    export VIGIL_BUCKET=${google_storage_bucket.raw.name}
    export VIGIL_MODEL_FLASH=${var.model_flash}
    export VIGIL_MODEL_PRO=${var.model_pro}
    export VIGIL_EMBED_MODEL=${var.embed_model}
  EOT
}
