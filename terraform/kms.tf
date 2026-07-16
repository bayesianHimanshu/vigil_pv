###############################################################################
# Cloud KMS - CMEK for BigQuery + Cloud Storage (diagram: CMEK Encryption).
# Gated on var.enable_cmek. Keys are regional so they must match the region of
# the resources they protect.
###############################################################################

resource "google_kms_key_ring" "vigil" {
  count = var.enable_cmek ? 1 : 0

  name     = "vigil-keyring"
  location = var.region
  project  = var.project_id

  depends_on = [time_sleep.after_apis]
}

resource "google_kms_crypto_key" "bq" {
  count = var.enable_cmek ? 1 : 0

  name            = "vigil-bigquery"
  key_ring        = google_kms_key_ring.vigil[0].id
  rotation_period = var.kms_key_rotation_period
  purpose         = "ENCRYPT_DECRYPT"
  labels          = var.labels

  lifecycle {
    prevent_destroy = false
  }
}

resource "google_kms_crypto_key" "gcs" {
  count = var.enable_cmek ? 1 : 0

  name            = "vigil-storage"
  key_ring        = google_kms_key_ring.vigil[0].id
  rotation_period = var.kms_key_rotation_period
  purpose         = "ENCRYPT_DECRYPT"
  labels          = var.labels

  lifecycle {
    prevent_destroy = false
  }
}

# The BigQuery encryption service agent must be able to use the BQ key before a
# CMEK-encrypted dataset can be created.
resource "google_kms_crypto_key_iam_member" "bq_agent" {
  count = var.enable_cmek ? 1 : 0

  crypto_key_id = google_kms_crypto_key.bq[0].id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${data.google_bigquery_default_service_account.bq.email}"
}

# The Cloud Storage service agent must be able to use the GCS key before a
# CMEK-encrypted bucket can write objects.
resource "google_kms_crypto_key_iam_member" "gcs_agent" {
  count = var.enable_cmek ? 1 : 0

  crypto_key_id = google_kms_crypto_key.gcs[0].id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${data.google_storage_project_service_account.gcs.email_address}"
}
