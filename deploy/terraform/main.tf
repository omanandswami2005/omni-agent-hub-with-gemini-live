# Omni — Terraform Infrastructure
#
# Provisions GCP resources for the Omni platform:
# - Cloud Run (backend API)
# - Firestore (data storage)
# - Firebase Auth (authentication)
# - Cloud Storage (file storage)
# - Secret Manager (secrets)
# - Artifact Registry (container images)
# - Cloud Logging, Monitoring, Trace (observability)

terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }

  # TODO: Configure remote state backend
  # backend "gcs" {
  #   bucket = "omni-terraform-state"
  #   prefix = "terraform/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# --- Artifact Registry ---
resource "google_artifact_registry_repository" "omni" {
  location      = var.region
  repository_id = "omni"
  format        = "DOCKER"
  description   = "Omni container images"
}

# --- Cloud Run Service ---
resource "google_cloud_run_v2_service" "backend" {
  name     = "omni-backend"
  location = var.region

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/omni/backend:latest"

      ports {
        container_port = 8080
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "FIREBASE_PROJECT_ID"
        value = var.project_id
      }

      env {
        name = "E2B_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.e2b_api_key.secret_id
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    session_affinity = true # Important for WebSocket connections
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

# --- Allow unauthenticated access (Firebase Auth handles app-level auth) ---
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# --- Cloud Storage ---
resource "google_storage_bucket" "omni_assets" {
  name          = "${var.project_id}-omni-assets"
  location      = var.region
  force_destroy = false
  uniform_bucket_level_access = true
}

# --- Secret Manager ---
resource "google_secret_manager_secret" "e2b_api_key" {
  secret_id = "e2b-api-key"
  replication {
    auto {}
  }
}

# --- Firestore ---
resource "google_firestore_database" "default" {
  provider    = google-beta
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
}
