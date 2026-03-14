#!/usr/bin/env bash
# =============================================================================
# fresh-start.sh — Clean ALL data from GCP while keeping infrastructure intact.
#
# Cleans:
#   1. Cloud Run — delete all old (inactive) revisions
#   2. Cloud Build — clear source archives in run-sources bucket
#   3. Artifact Registry — remove old/untagged container images
#   4. Firestore — wipe sessions, personas, memories, client_presence
#   5. Vertex AI — delete Agent Engine sessions & memories
#   6. GCS Storage — empty the omni-artifacts bucket
#   7. Secret Manager — delete old secret versions (keep latest)
#   8. Local terraform state — remove .tfstate files if present
#
# Keeps (app stays fully functional):
#   - Cloud Run services (omni-backend with current active revision)
#   - Firebase Auth users
#   - Firebase Hosting deployment
#   - Secret Manager secrets (structure, latest version)
#   - GCS buckets (structure, not contents)
#   - Artifact Registry repos (structure)
#   - All GCP APIs enabled
#
# Usage:
#   ./fresh-start.sh                     # uses gcloud default project
#   ./fresh-start.sh <project-id>        # explicit project
#   DRY_RUN=1 ./fresh-start.sh           # preview what would be deleted
#
# =============================================================================

set -euo pipefail

# --- Windows / Python 3.14 compatibility for gcloud CLI ----------------------
if [[ -z "${CLOUDSDK_PYTHON:-}" ]]; then
  for _py in "/c/Program Files/Python314/python.exe" "/c/Python312/python.exe"; do
    if [[ -f "$_py" ]]; then export CLOUDSDK_PYTHON="$_py"; break; fi
  done
fi

# --- Colours ------------------------------------------------------------------
BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${BLUE}[CLEAN]${NC} $*"; }
ok()   { echo -e "${GREEN}    ✓${NC} $*"; }
warn() { echo -e "${YELLOW}    ⚠${NC} $*"; }
err()  { echo -e "${RED}    ✗${NC} $*" >&2; }
step() { echo; echo -e "${CYAN}═══ $* ═══${NC}"; }
dry()  { echo -e "${YELLOW}  [DRY-RUN]${NC} $*"; }

DRY_RUN="${DRY_RUN:-}"

run_cmd() {
  if [[ -n "${DRY_RUN}" ]]; then
    dry "$*"
  else
    eval "$@"
  fi
}

# --- Config -------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
REGION="us-central1"

# Firestore collections to wipe
FIRESTORE_COLLECTIONS=("sessions" "personas" "memories" "client_presence")

# GCS buckets to clear (contents only — buckets kept)
ARTIFACTS_BUCKET="gemini-live-hackathon-2026-omni-artifacts"
CLOUDBUILD_BUCKET="gemini-live-hackathon-2026_cloudbuild"
RUN_SOURCES_BUCKET="run-sources-gemini-live-hackathon-2026-us-central1"

# Vertex AI — dynamically discover all reasoning engines
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}" --format="value(projectNumber)" 2>/dev/null || echo "")

if [[ -z "${PROJECT_ID}" ]]; then
  err "No GCP project. Run: gcloud config set project <project-id>"
  exit 1
fi

echo
echo "╔══════════════════════════════════════════════════╗"
echo "║       Omni — Fresh Start (Data Cleanup)          ║"
echo "╚══════════════════════════════════════════════════╝"
log "Project : ${PROJECT_ID}"
log "Region  : ${REGION}"
[[ -n "${DRY_RUN}" ]] && warn "DRY_RUN mode — nothing will be deleted"
echo

if [[ -z "${DRY_RUN}" ]]; then
  echo -e "${RED}⚠  WARNING: This will DELETE all user data (sessions, personas, memories,${NC}"
  echo -e "${RED}   stored files, old deployments) while keeping the app infrastructure.${NC}"
  echo
  read -r -p "Type 'yes' to confirm: " CONFIRM
  if [[ "${CONFIRM}" != "yes" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

ERRORS=0

# =============================================================================
# 1. CLOUD RUN — Delete old (inactive) revisions
# =============================================================================
step "1/8  Cloud Run — Prune inactive revisions"

ACTIVE_REV=$(gcloud run services describe omni-backend \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format='value(status.traffic[0].revisionName)' 2>/dev/null || echo "")

if [[ -z "${ACTIVE_REV}" ]]; then
  warn "Could not determine active revision — skipping"
else
  ok "Active revision: ${ACTIVE_REV} (keeping)"
  OLD_REVS=$(gcloud run revisions list \
    --service=omni-backend --region="${REGION}" --project="${PROJECT_ID}" \
    --format='value(name)' 2>/dev/null | grep -v "^${ACTIVE_REV}$" || true)

  if [[ -z "${OLD_REVS}" ]]; then
    ok "No old revisions to delete"
  else
    COUNT=$(echo "${OLD_REVS}" | wc -l | tr -d ' ')
    log "Deleting ${COUNT} old revisions..."
    while IFS= read -r rev; do
      run_cmd "gcloud run revisions delete '${rev}' --region='${REGION}' --project='${PROJECT_ID}' --quiet 2>/dev/null" && ok "Deleted ${rev}" || { warn "Failed: ${rev}"; ((ERRORS++)) || true; }
    done <<< "${OLD_REVS}"
  fi
fi

# =============================================================================
# 2. GCS — Clear storage bucket contents
# =============================================================================
step "2/8  GCS — Clear bucket contents"

for BUCKET in "${ARTIFACTS_BUCKET}" "${CLOUDBUILD_BUCKET}" "${RUN_SOURCES_BUCKET}"; do
  log "Clearing gs://${BUCKET}/..."
  if [[ -n "${DRY_RUN}" ]]; then
    dry "gcloud storage rm -r gs://${BUCKET}/**"
  else
    gcloud storage rm "gs://${BUCKET}/**" --recursive 2>/dev/null && ok "Cleared ${BUCKET}" || warn "Bucket ${BUCKET} already empty or not found"
  fi
done

# =============================================================================
# 3. FIRESTORE — Wipe all collections
# =============================================================================
step "3/8  Firestore — Delete all collections"

for COLL in "${FIRESTORE_COLLECTIONS[@]}"; do
  log "Deleting collection: ${COLL}"
  if [[ -n "${DRY_RUN}" ]]; then
    dry "gcloud firestore documents delete --collection-group=${COLL} --all-documents"
  else
    # Use firebase CLI if available, otherwise gcloud
    if command -v firebase &>/dev/null; then
      firebase firestore:delete "${COLL}" --project="${PROJECT_ID}" --recursive --force 2>/dev/null \
        && ok "Deleted ${COLL}" || { warn "Failed to delete ${COLL}"; ((ERRORS++)) || true; }
    else
      # Fallback: use gcloud firestore
      gcloud firestore databases delete-all-documents \
        --project="${PROJECT_ID}" --quiet 2>/dev/null \
        && ok "Deleted all Firestore documents" \
        || { warn "gcloud firestore wipe failed — install Firebase CLI for per-collection delete"; ((ERRORS++)) || true; }
      break  # gcloud approach deletes everything at once
    fi
  fi
done

# =============================================================================
# 4. VERTEX AI — Delete all Reasoning Engines (Agent Engines)
# =============================================================================
step "4/8  Vertex AI — Delete all Reasoning Engines"

if [[ -z "${PROJECT_NUMBER}" ]]; then
  warn "Could not determine project number — skipping Vertex AI cleanup"
  ((ERRORS++)) || true
else
  log "Project number: ${PROJECT_NUMBER}"

  if [[ -n "${DRY_RUN}" ]]; then
    dry "curl -X GET .../reasoningEngines (then DELETE each)"
  else
    ACCESS_TOKEN=$(gcloud auth print-access-token 2>/dev/null || echo "")
    if [[ -n "${ACCESS_TOKEN}" ]]; then
      API_BASE="https://${REGION}-aiplatform.googleapis.com/v1beta1"
      ENGINES_URL="${API_BASE}/projects/${PROJECT_NUMBER}/locations/${REGION}/reasoningEngines"

      # List all reasoning engines
      ENGINE_NAMES=$(curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
        "${ENGINES_URL}" 2>/dev/null | grep -o '"name": *"[^"]*"' | cut -d'"' -f4 || true)

      if [[ -z "${ENGINE_NAMES}" ]]; then
        ok "No reasoning engines found"
      else
        E_COUNT=$(echo "${ENGINE_NAMES}" | wc -l | tr -d ' ')
        log "Found ${E_COUNT} reasoning engines — deleting..."
        PASS=1
        while [[ -n "${ENGINE_NAMES}" && ${PASS} -le 3 ]]; do
          log "  Pass ${PASS}..."
          while IFS= read -r name; do
            [[ -z "${name}" ]] && continue
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
              -H "Authorization: Bearer ${ACCESS_TOKEN}" \
              "${API_BASE}/${name}" 2>/dev/null || echo "000")
            case "${HTTP_CODE}" in
              200) ok "Deleted $(basename "${name}")" ;;
              400) ;; # Already being deleted async
              429) warn "Rate limited — will retry next pass" ;;
              *)   warn "Unexpected ${HTTP_CODE} for $(basename "${name}")" ;;
            esac
            sleep 2
          done <<< "${ENGINE_NAMES}"
          sleep 10
          # Re-check remaining
          ENGINE_NAMES=$(curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" \
            "${ENGINES_URL}" 2>/dev/null | grep -o '"name": *"[^"]*"' | cut -d'"' -f4 || true)
          ((PASS++))
        done
        if [[ -n "${ENGINE_NAMES}" ]]; then
          REMAINING=$(echo "${ENGINE_NAMES}" | wc -l | tr -d ' ')
          warn "${REMAINING} engines still async-deleting — they will clean up on their own"
        else
          ok "All reasoning engines deleted"
        fi
      fi
    else
      warn "Could not get access token — skipping Vertex AI cleanup"
      ((ERRORS++)) || true
    fi
  fi
fi

# =============================================================================
# 5. ARTIFACT REGISTRY — Clean old container images
# =============================================================================
step "5/8  Artifact Registry — Clean old images"

log "Removing untagged images from omni repo..."
if [[ -n "${DRY_RUN}" ]]; then
  dry "gcloud artifacts docker images delete (untagged)"
else
  # List all images, delete untagged ones (keep tagged/latest)
  IMAGES=$(gcloud artifacts docker images list \
    "us-central1-docker.pkg.dev/${PROJECT_ID}/omni" \
    --include-tags --format='csv[no-heading](IMAGE,DIGEST,TAGS)' 2>/dev/null || true)

  if [[ -z "${IMAGES}" ]]; then
    ok "No images found in Artifact Registry"
  else
    DELETED=0
    while IFS=',' read -r image digest tags; do
      # Delete images with no tags (orphaned layers)
      if [[ -z "${tags}" || "${tags}" == " " ]]; then
        gcloud artifacts docker images delete "${image}@${digest}" \
          --project="${PROJECT_ID}" --quiet --delete-tags 2>/dev/null \
          && ((DELETED++)) || true
      fi
    done <<< "${IMAGES}"
    ok "Cleaned ${DELETED} untagged images"
  fi
fi

# =============================================================================
# 6. SECRET MANAGER — Remove old secret versions (keep latest)
# =============================================================================
step "6/8  Secret Manager — Prune old versions"

SECRETS=$(gcloud secrets list --project="${PROJECT_ID}" --format='value(name)' 2>/dev/null || true)

if [[ -z "${SECRETS}" ]]; then
  ok "No secrets found"
else
  while IFS= read -r secret_name; do
    [[ -z "${secret_name}" ]] && continue
    log "Secret: ${secret_name}"

    # List all versions except 'latest' (the most recent enabled one)
    VERSIONS=$(gcloud secrets versions list "${secret_name}" \
      --project="${PROJECT_ID}" \
      --format='value(name)' --sort-by='~createTime' 2>/dev/null || true)

    FIRST=true
    while IFS= read -r ver; do
      [[ -z "${ver}" ]] && continue
      if [[ "${FIRST}" == "true" ]]; then
        ok "  Keeping latest version: ${ver}"
        FIRST=false
        continue
      fi
      run_cmd "gcloud secrets versions destroy '${ver}' --secret='${secret_name}' --project='${PROJECT_ID}' --quiet 2>/dev/null" \
        && ok "  Destroyed version: ${ver}" || warn "  Failed: ${ver}"
    done <<< "${VERSIONS}"
  done <<< "${SECRETS}"
fi

# =============================================================================
# 7. LOCAL CLEANUP — Terraform state, caches
# =============================================================================
step "7/8  Local — Terraform state & caches"

TF_DIR="${ROOT_DIR}/deploy/terraform"
if [[ -f "${TF_DIR}/terraform.tfstate" ]]; then
  run_cmd "rm -f '${TF_DIR}/terraform.tfstate' '${TF_DIR}/terraform.tfstate.backup'" \
    && ok "Removed terraform.tfstate" || warn "Failed"
else
  ok "No terraform state files found"
fi

if [[ -d "${TF_DIR}/.terraform" ]]; then
  run_cmd "rm -rf '${TF_DIR}/.terraform'" \
    && ok "Removed .terraform directory" || warn "Failed"
else
  ok "No .terraform directory"
fi

# Clean local test output
if [[ -d "${ROOT_DIR}/backend/test_output" ]]; then
  run_cmd "rm -rf '${ROOT_DIR}/backend/test_output'/*" \
    && ok "Cleared backend/test_output" || warn "Failed"
fi

# =============================================================================
# 8. FIREBASE HOSTING — Clean old versions (keep active)
# =============================================================================
step "8/8  Firebase Hosting — Prune old versions"

if command -v firebase &>/dev/null; then
  log "Cleaning up expired/old hosting versions..."
  if [[ -n "${DRY_RUN}" ]]; then
    dry "firebase hosting:channel:delete (old channels)"
  else
    # Clean up preview channels if any
    firebase hosting:channel:list --project="${PROJECT_ID}" 2>/dev/null | \
      grep -v "live" | awk '{print $1}' | while read -r channel; do
        [[ -z "${channel}" ]] && continue
        firebase hosting:channel:delete "${channel}" --project="${PROJECT_ID}" --force 2>/dev/null \
          && ok "Deleted channel: ${channel}" || true
      done
    ok "Firebase Hosting cleaned"
  fi
else
  warn "Firebase CLI not installed — skipping hosting cleanup"
  warn "Install with: npm install -g firebase-tools"
fi

# =============================================================================
# SUMMARY
# =============================================================================
echo
echo "╔══════════════════════════════════════════════════╗"
echo "║              Cleanup Complete                     ║"
echo "╚══════════════════════════════════════════════════╝"

if [[ -n "${DRY_RUN}" ]]; then
  warn "DRY RUN — nothing was actually deleted"
  warn "Remove DRY_RUN=1 to execute for real"
elif [[ ${ERRORS} -gt 0 ]]; then
  warn "${ERRORS} operations had issues (see warnings above)"
else
  ok "All cleanup completed successfully"
fi

echo
log "What was preserved (app still works):"
ok "  Cloud Run service: omni-backend (active revision)"
ok "  Firebase Auth: all users intact"
ok "  Firebase Hosting: live deployment"
ok "  Secret Manager: secrets (latest versions)"
ok "  GCS buckets: exist (contents cleared)"
ok "  Artifact Registry: repo structure"
echo
log "Your app is now a fresh start — re-deploy to create new data."
echo
