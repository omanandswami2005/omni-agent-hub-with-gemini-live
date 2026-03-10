variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "image_tag" {
  description = "Docker image tag for the backend container"
  type        = string
  default     = "latest"
}

variable "domain" {
  description = "Custom domain for the application (optional)"
  type        = string
  default     = ""
}
