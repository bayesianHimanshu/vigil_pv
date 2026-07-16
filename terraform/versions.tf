terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.13"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.13"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }

  # Uncomment to keep state in GCS instead of locally (recommended for teams).
  # Create the bucket first, then run `terraform init -migrate-state`.
  # backend "gcs" {
  #   bucket = "vigil-500820-tfstate"
  #   prefix = "vigil"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # discoveryengine + some Vertex APIs require a quota/billing project header
  # when authenticating with user ADC. Route it to this project.
  billing_project       = var.project_id
  user_project_override = true
}

provider "google-beta" {
  project = var.project_id
  region  = var.region

  billing_project       = var.project_id
  user_project_override = true
}
