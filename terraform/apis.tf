###############################################################################
# Project services (APIs). Everything downstream depends on these so the first
# apply enables them before resources are created.
###############################################################################

locals {
  required_services = [
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "bigquery.googleapis.com",
    "bigquerystorage.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",      # Vertex AI: Gemini models + Agent Engine
    "firestore.googleapis.com",       # case workflow state
    "discoveryengine.googleapis.com", # Vertex AI Search + Gemini Enterprise surface
    "cloudkms.googleapis.com",        # CMEK
    "logging.googleapis.com",         # Cloud Audit Logs sink target
    "monitoring.googleapis.com",
  ]

  # Network/perimeter APIs only when those modules are switched on.
  conditional_services = concat(
    var.enable_network ? ["compute.googleapis.com", "servicenetworking.googleapis.com"] : [],
    var.enable_vpc_sc ? ["accesscontextmanager.googleapis.com"] : [],
  )
}

resource "google_project_service" "services" {
  for_each = toset(concat(local.required_services, local.conditional_services))

  project = var.project_id
  service = each.value

  disable_on_destroy         = false
  disable_dependent_services = false
}

# Give newly-enabled APIs a moment to fully propagate service agents before the
# first resources (and KMS service-agent grants) try to use them.
resource "time_sleep" "after_apis" {
  depends_on      = [google_project_service.services]
  create_duration = "30s"
}
