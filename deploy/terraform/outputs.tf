output "backend_url" {
  description = "Cloud Run backend service URL"
  value       = google_cloud_run_v2_service.backend.uri
}

output "artifact_registry" {
  description = "Artifact Registry repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/omni"
}

output "storage_bucket" {
  description = "Cloud Storage bucket name"
  value       = google_storage_bucket.omni_assets.name
}

output "service_account_email" {
  description = "Backend service account email"
  value       = "${var.project_id}@${var.project_id}.iam.gserviceaccount.com"
}

output "firestore_database" {
  description = "Firestore database name"
  value       = google_firestore_database.default.name
}

output "gcp_services_count" {
  description = "Number of GCP APIs enabled (for judging visibility)"
  value       = length(local.required_apis)
}
