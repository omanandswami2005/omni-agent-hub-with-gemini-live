#!/usr/bin/env bash
# Deploy Omni to GCP — build images, push, terraform apply, deploy.
#
# Usage: ./deploy.sh [project-id] [region]
#
# Modes:
#   SKIP_BUILD=1 ./deploy.sh    — skip Docker build, run Terraform only
#   SKIP_TF=1    ./deploy.sh    — skip Terraform, deploy via gcloud only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/../../.."
PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${2:-us-central1}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/omni/backend"
TAG="${IMAGE_TAG:-latest}"

echo "=== Omni Deployment ==="
echo "Project:  ${PROJECT_ID}"
echo "Region:   ${REGION}"
echo "Image:    ${IMAGE}:${TAG}"
echo

# --- 1. Build & push Docker image ---
if [[ -z "${SKIP_BUILD:-}" ]]; then
  echo "=== Building backend image ==="
  docker build -t "${IMAGE}:${TAG}" "${ROOT_DIR}/backend/"

  echo "=== Authenticating Docker with Artifact Registry ==="
  gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

  echo "=== Pushing to Artifact Registry ==="
  docker push "${IMAGE}:${TAG}"
else
  echo "=== Skipping Docker build (SKIP_BUILD=1) ==="
fi

# --- 2. Terraform apply ---
if [[ -z "${SKIP_TF:-}" ]]; then
  echo "=== Running Terraform ==="
  cd "${ROOT_DIR}/deploy/terraform"

  terraform init -input=false
  terraform apply -auto-approve \
    -var="project_id=${PROJECT_ID}" \
    -var="region=${REGION}" \
    -var="image_tag=${TAG}"

  echo "=== Terraform outputs ==="
  terraform output
  cd "${SCRIPT_DIR}"
else
  echo "=== Skipping Terraform (SKIP_TF=1) ==="
fi

# --- 3. Deploy to Cloud Run (if skipping Terraform) ---
if [[ -n "${SKIP_TF:-}" ]]; then
  echo "=== Deploying to Cloud Run via gcloud ==="
  gcloud run deploy omni-backend \
    --image="${IMAGE}:${TAG}" \
    --platform=managed \
    --region="${REGION}" \
    --allow-unauthenticated \
    --session-affinity \
    --min-instances=0 \
    --max-instances=10 \
    --memory=2Gi \
    --cpu=2 \
    --port=8080
fi

# --- 4. Print service URL ---
echo
echo "=== Deployment complete ==="
BACKEND_URL=$(gcloud run services describe omni-backend --region="${REGION}" --format='value(status.url)' 2>/dev/null || echo "(not yet available)")
echo "Backend URL: ${BACKEND_URL}"
