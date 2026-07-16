###############################################################################
# Core project / location
###############################################################################

variable "project_id" {
  description = "GCP project id to deploy Project VIGIL into."
  type        = string
}

variable "region" {
  description = "Default region for regional resources (Vertex AI, KMS, Firestore, buckets)."
  type        = string
  default     = "us-central1"
}

variable "bq_location" {
  description = "BigQuery dataset location. Use the region (us-central1) or a multi-region (US/EU). Must match where Vertex AI runs for low-latency joins."
  type        = string
  default     = "us-central1"
}

variable "discovery_location" {
  description = "Vertex AI Search (Discovery Engine) location: global, us, or eu."
  type        = string
  default     = "global"
}

variable "labels" {
  description = "Common labels applied to all labelable resources."
  type        = map(string)
  default = {
    app        = "vigil"
    system     = "pharmacovigilance"
    managed_by = "terraform"
  }
}

###############################################################################
# BigQuery
###############################################################################

variable "dataset_id" {
  description = "BigQuery dataset id (the demo uses a single dataset; sql/data_model.sql targets pv_vigil)."
  type        = string
  default     = "pv_vigil"
}

variable "model_flash" {
  description = "Gemini model for high-throughput stages (triage/extraction/coding). gemini-3-* are placeholders; gemini-2.5-flash is the live Model Garden id."
  type        = string
  default     = "gemini-2.5-flash"
}

variable "model_pro" {
  description = "Gemini model for reasoning stages (assessment/narrative/signal)."
  type        = string
  default     = "gemini-2.5-pro"
}

variable "embed_model" {
  description = "Vertex embedding model for grounding."
  type        = string
  default     = "text-embedding-005"
}

variable "bq_delete_contents_on_destroy" {
  description = "If true, `terraform destroy` will drop the dataset even if it contains tables. Keep false in anything resembling production."
  type        = bool
  default     = false
}

###############################################################################
# Storage
###############################################################################

variable "raw_bucket_name" {
  description = "GCS bucket for raw VAERS landing + lineage copies. Defaults to <project>-vigil-raw."
  type        = string
  default     = ""
}

variable "staging_bucket_name" {
  description = "GCS bucket used as the Vertex AI Agent Engine staging bucket. Defaults to <project>-vigil-agent-staging."
  type        = string
  default     = ""
}

variable "force_destroy_buckets" {
  description = "Allow `terraform destroy` to delete non-empty buckets. Keep false in production."
  type        = bool
  default     = false
}

###############################################################################
# Firestore (case workflow state)
###############################################################################

variable "firestore_location" {
  description = "Firestore database location (regional, e.g. us-central1, or multi-region nam5/eur3)."
  type        = string
  default     = "us-central1"
}

variable "create_firestore_indexes" {
  description = "Create the composite index supporting the review-queue query on cases/{vaers_id}."
  type        = bool
  default     = true
}

###############################################################################
# Governance toggles
###############################################################################

variable "enable_cmek" {
  description = "Provision Cloud KMS keys and apply CMEK to BigQuery + Cloud Storage (the diagram's CMEK Encryption box)."
  type        = bool
  default     = true
}

variable "kms_key_rotation_period" {
  description = "Rotation period for CMEK keys (seconds). 7776000s = 90 days."
  type        = string
  default     = "7776000s"
}

variable "audit_log_services" {
  description = "Services to enable Data Access audit logs on (Cloud Audit Logs box). ADMIN_READ/DATA_READ/DATA_WRITE."
  type        = list(string)
  default = [
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
  ]
}

###############################################################################
# Vertex AI Search (Discovery Engine) - grounding corpus
###############################################################################

variable "enable_vertex_ai_search" {
  description = "Create a Vertex AI Search (Discovery Engine) data store as the production grounding corpus for MedDRA PTs. The default pipeline grounds in-process; this readies the production swap."
  type        = bool
  default     = true
}

variable "enable_search_engine" {
  description = "Also create a Discovery Engine search engine (with the LLM add-on) on top of the data store. Off by default to avoid the add-on cost."
  type        = bool
  default     = false
}

###############################################################################
# Optional network + VPC Service Controls (the diagram's outer perimeter)
###############################################################################

variable "enable_network" {
  description = "Create a dedicated VPC + subnet. Only needed if you later add compute (Cloud Run ingestion) or want a perimeter to attach. Off by default for the lean footprint."
  type        = bool
  default     = false
}

variable "enable_vpc_sc" {
  description = "Create a VPC Service Controls perimeter. REQUIRES a GCP Organization (Access Context Manager is org-scoped). The target project vigil-500820 has no org, so this stays off."
  type        = bool
  default     = false
}

variable "access_policy_id" {
  description = "Existing Access Context Manager policy id (numeric). Required only when enable_vpc_sc = true."
  type        = string
  default     = ""
}

variable "vpc_sc_restricted_services" {
  description = "APIs to lock inside the VPC-SC perimeter when enable_vpc_sc = true."
  type        = list(string)
  default = [
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
    "discoveryengine.googleapis.com",
    "firestore.googleapis.com",
  ]
}
