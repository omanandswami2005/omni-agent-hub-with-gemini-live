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
      image = "${var.region}-docker.pkg.dev/${var.project_id}/omni/backend:${var.image_tag}"

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
          memory = "2Gi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    session_affinity = true # Important for WebSocket connections

    service_account = google_service_account.backend.email
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

# --- Enabled GCP APIs ---
# Managed declaratively to ensure reproducibility
locals {
  required_apis = [
    "aiplatform.googleapis.com",
    "generativelanguage.googleapis.com",
    "firestore.googleapis.com",
    "firebase.googleapis.com",
    "identitytoolkit.googleapis.com",
    "storage.googleapis.com",
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudtrace.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.required_apis)
  service  = each.value

  disable_on_destroy = false
}

# --- Cloud Monitoring Uptime Check ---
resource "google_monitoring_uptime_check_config" "backend_health" {
  display_name = "omni-backend-health"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = trimprefix(google_cloud_run_v2_service.backend.uri, "https://")
    }
  }

  depends_on = [google_project_service.apis]
}

# --- Cloud Monitoring Alert Policy (high latency) ---
resource "google_monitoring_alert_policy" "high_latency" {
  display_name = "Omni Backend High Latency"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run request latency > 5s"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/request_latencies\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5000

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_99"
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# --- Service Account & IAM Bindings ---
resource "google_service_account" "backend" {
  account_id   = "omni-backend"
  display_name = "Omni Backend Service Account"
}

resource "google_project_iam_member" "backend_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_firebase" {
  project = var.project_id
  role    = "roles/firebase.admin"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_tracing" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

# --- Firebase Hosting (Dashboard SPA) ---
resource "google_firebase_hosting_site" "dashboard" {
  provider = google-beta
  project  = var.project_id
  site_id  = "${var.project_id}-dashboard"
}

resource "google_firebase_hosting_channel" "live" {
  provider   = google-beta
  site_id    = google_firebase_hosting_site.dashboard.site_id
  channel_id = "live"
}
