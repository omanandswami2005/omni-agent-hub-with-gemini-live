#!/usr/bin/env bash
# Deploy Omni backend to Cloud Run.
#
# Usage: ./deploy.sh [project-id] [region]

set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project)}"
REGION="${2:-us-central1}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/omni/backend"

echo "=== Building backend image ==="
docker build -t "${IMAGE}:latest" ../backend/

echo "=== Pushing to Artifact Registry ==="
docker push "${IMAGE}:latest"

echo "=== Deploying to Cloud Run ==="
gcloud run deploy omni-backend \
  --image="${IMAGE}:latest" \
  --platform=managed \
  --region="${REGION}" \
  --allow-unauthenticated \
  --session-affinity \
  --min-instances=0 \
  --max-instances=10 \
  --memory=1Gi \
  --cpu=2 \
  --port=8080

echo "=== Done ==="
gcloud run services describe omni-backend --region="${REGION}" --format='value(status.url)'
