#!/usr/bin/env bash
# =============================================================================
# deploy-all.sh — Build & deploy backend (Cloud Run) + dashboard (Firebase Hosting)
#
# Usage:
#   ./deploy-all.sh                       # uses gcloud default project / us-central1
#   ./deploy-all.sh <project-id>          # explicit project
#   ./deploy-all.sh <project-id> <region> # explicit project + region
#
# Environment overrides:
#   IMAGE_TAG=v1.2.3    ./deploy-all.sh   # use a specific image tag (default: latest)
#   SKIP_BACKEND=1      ./deploy-all.sh   # skip backend build+deploy
#   SKIP_DASHBOARD=1    ./deploy-all.sh   # skip dashboard build+deploy
#   SKIP_BUILD=1        ./deploy-all.sh   # skip Docker build (re-deploy existing image)
#
# Prerequisites:
#   - gcloud CLI authenticated  (gcloud auth login)
#   - firebase CLI installed    (for dashboard deploy)
#   - pnpm installed            (for dashboard build)
#   - Artifact Registry repo "omni" already exists (run setup-gcp.sh once first)
# =============================================================================

set -euo pipefail

# --- Windows / Python 3.14 compatibility for gcloud CLI ----------------------
# gcloud uses Python internally; Python 3.14 changed multiprocessing defaults
# that break gcloud on Windows. Force it to use a compatible Python if available.
if [[ -z "${CLOUDSDK_PYTHON:-}" ]]; then
  for _py in "/c/Program Files/Python314/python.exe" "/c/Python312/python.exe"; do
    if [[ -f "$_py" ]]; then export CLOUDSDK_PYTHON="$_py"; break; fi
  done
fi

# --- Colours ------------------------------------------------------------------
BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${BLUE}[DEPLOY]${NC} $*"; }
ok()   { echo -e "${GREEN}    ✓${NC} $*"; }
warn() { echo -e "${YELLOW}    ⚠${NC} $*"; }
err()  { echo -e "${RED}    ✗${NC} $*" >&2; }
step() { echo; echo -e "${BLUE}═══ $* ═══${NC}"; }

# --- Config -------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${2:-us-central1}"
TAG="${IMAGE_TAG:-latest}"
REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/omni"
BACKEND_IMAGE="${REGISTRY}/backend"

if [[ -z "${PROJECT_ID}" ]]; then
  err "No GCP project set. Run: gcloud config set project <project-id>"
  err "Or pass it as the first argument: ./deploy-all.sh <project-id>"
  exit 1
fi

echo
echo "╔══════════════════════════════════════════════════╗"
echo "║        Omni — Full Stack GCP Deploy              ║"
echo "╚══════════════════════════════════════════════════╝"
log "Project  : ${PROJECT_ID}"
log "Region   : ${REGION}"
log "Tag      : ${TAG}"
log "Backend  : Cloud Run (${BACKEND_IMAGE}:${TAG})"
log "Dashboard: Firebase Hosting (${PROJECT_ID}.web.app)"
[[ -n "${SKIP_BACKEND:-}"   ]] && warn "SKIP_BACKEND=1  — backend will be skipped"
[[ -n "${SKIP_DASHBOARD:-}" ]] && warn "SKIP_DASHBOARD=1 — dashboard will be skipped"
[[ -n "${SKIP_BUILD:-}"     ]] && warn "SKIP_BUILD=1    — Docker build will be skipped"

# =============================================================================
# BACKEND — Docker → Artifact Registry → Cloud Run
# =============================================================================
if [[ -z "${SKIP_BACKEND:-}" ]]; then

  # --- Authenticate Docker with Artifact Registry (needed for Cloud Run pulls) ---
  step "Backend → Artifact Registry auth"
  gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
  ok "Authenticated"

  if [[ -z "${SKIP_BUILD:-}" ]]; then
    step "Backend — Cloud Build (remote Docker build)"
    gcloud builds submit \
      --tag="${BACKEND_IMAGE}:${TAG}" \
      --project="${PROJECT_ID}" \
      --timeout=900 \
      "${ROOT_DIR}/backend/"
    ok "Built & pushed ${BACKEND_IMAGE}:${TAG}"
  else
    warn "Skipping backend build (SKIP_BUILD=1)"
  fi

  step "Backend — Deploy to Cloud Run"
  gcloud run deploy omni-backend \
    --image="${BACKEND_IMAGE}:${TAG}" \
    --platform=managed \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --allow-unauthenticated \
    --session-affinity \
    --min-instances=0 \
    --max-instances=10 \
    --memory=2Gi \
    --cpu=2 \
    --port=8080 \
    --env-vars-file="${ROOT_DIR}/backend/cloud-run-env.yaml"

  BACKEND_URL=$(gcloud run services describe omni-backend \
    --region="${REGION}" --project="${PROJECT_ID}" \
    --format='value(status.url)' 2>/dev/null || echo "(unavailable)")
  ok "Backend live: ${BACKEND_URL}"

else
  warn "Skipping backend (SKIP_BACKEND=1)"
  BACKEND_URL=$(gcloud run services describe omni-backend \
    --region="${REGION}" --project="${PROJECT_ID}" \
    --format='value(status.url)' 2>/dev/null || echo "(not deployed)")
fi

# =============================================================================
# DASHBOARD — pnpm build → Firebase Hosting
# =============================================================================
if [[ -z "${SKIP_DASHBOARD:-}" ]]; then

  step "Dashboard — Build (Vite)"
  cd "${ROOT_DIR}/dashboard"
  pnpm install --frozen-lockfile 2>/dev/null || pnpm install
  pnpm run build
  ok "Built dashboard/dist"

  step "Dashboard — Deploy to Firebase Hosting"
  cd "${ROOT_DIR}"
  firebase deploy --only hosting --project="${PROJECT_ID}"
  DASHBOARD_URL="https://${PROJECT_ID}.web.app"
  ok "Dashboard live: ${DASHBOARD_URL}"

else
  warn "Skipping dashboard (SKIP_DASHBOARD=1)"
  DASHBOARD_URL="https://${PROJECT_ID}.web.app"
fi

# =============================================================================
# Summary
# =============================================================================
echo
echo "╔══════════════════════════════════════════════════╗"
echo "║              Deployment Complete                 ║"
echo "╚══════════════════════════════════════════════════╝"
ok "Backend  : ${BACKEND_URL}"
ok "Dashboard: ${DASHBOARD_URL}"
echo
log "Quick test:"
log "  curl ${BACKEND_URL}/health"
log "  open ${DASHBOARD_URL}"
echo
