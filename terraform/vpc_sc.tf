###############################################################################
# VPC Service Controls (diagram: "VPC Service Control Parameters").
#
# REQUIRES A GCP ORGANIZATION. Access Context Manager policies are created on an
# organization (or folder), never on a standalone project. The target project
# vigil-500820 has no organization, so this stays OFF (enable_vpc_sc = false)
# and the resources below produce zero objects.
#
# To use on an org-owned project:
#   1. enable_vpc_sc = true
#   2. set access_policy_id to your org's Access Context Manager policy id
#      (gcloud access-context-manager policies list --organization=ORG_ID)
#   3. apply. The perimeter then ring-fences the restricted services so data in
#      BigQuery / GCS / Vertex / Firestore can only be reached from inside it.
###############################################################################

resource "google_access_context_manager_service_perimeter" "vigil" {
  count = var.enable_vpc_sc ? 1 : 0

  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/vigil_perimeter"
  title  = "Project VIGIL perimeter"

  status {
    resources           = ["projects/${local.project_number}"]
    restricted_services = var.vpc_sc_restricted_services

    vpc_accessible_services {
      enable_restriction = true
      allowed_services   = var.vpc_sc_restricted_services
    }
  }

  lifecycle {
    ignore_changes = [status[0].access_levels]
  }
}
