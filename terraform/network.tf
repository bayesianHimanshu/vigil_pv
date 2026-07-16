###############################################################################
# Optional VPC + subnet (diagram: Virtual Private Cloud).
# Off by default - the lean, skip-ingestion footprint has no compute to place in
# a VPC. Flip enable_network = true if you later add the Cloud Run ingestion
# service or want a network to attach a VPC-SC perimeter to.
###############################################################################

resource "google_compute_network" "vigil" {
  count = var.enable_network ? 1 : 0

  name                    = "vigil-vpc"
  project                 = var.project_id
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  depends_on = [time_sleep.after_apis]
}

resource "google_compute_subnetwork" "vigil" {
  count = var.enable_network ? 1 : 0

  name                     = "vigil-subnet"
  project                  = var.project_id
  region                   = var.region
  network                  = google_compute_network.vigil[0].id
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true
}
