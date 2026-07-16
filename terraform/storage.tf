###############################################################################
# Cloud Storage
#   raw     - VAERS raw landing + lineage copies (loader.upload_to_gcs)
#   staging - Vertex AI Agent Engine staging bucket (code package on deploy)
# Both: uniform bucket-level access, public access blocked, versioned, CMEK.
###############################################################################

resource "google_storage_bucket" "raw" {
  name     = local.raw_bucket_name
  location = var.region
  project  = var.project_id

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy_buckets
  labels                      = var.labels

  versioning {
    enabled = true
  }

  dynamic "encryption" {
    for_each = var.enable_cmek ? [1] : []
    content {
      default_kms_key_name = google_kms_crypto_key.gcs[0].id
    }
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  depends_on = [google_kms_crypto_key_iam_member.gcs_agent]
}

resource "google_storage_bucket" "staging" {
  name     = local.staging_bucket_name
  location = var.region
  project  = var.project_id

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy_buckets
  labels                      = var.labels

  versioning {
    enabled = true
  }

  dynamic "encryption" {
    for_each = var.enable_cmek ? [1] : []
    content {
      default_kms_key_name = google_kms_crypto_key.gcs[0].id
    }
  }

  depends_on = [google_kms_crypto_key_iam_member.gcs_agent]
}
