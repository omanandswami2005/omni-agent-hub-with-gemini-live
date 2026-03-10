#!/usr/bin/env bash
# ============================================================================
# Omni — GCP Infrastructure Setup (Automated)
#
# Provisions all Google Cloud resources needed for the Omni platform:
#   - Enables 10+ GCP APIs (Vertex AI, Firestore, Firebase, GCS, etc.)
#   - Creates Firestore database (Native mode)
#   - Creates Cloud Storage bucket
#   - Creates Artifact Registry repository
#   - Creates service account with least-privilege IAM roles
#   - Downloads service account key for local development
#   - Creates Secret Manager secret for E2B API key
#   - Populates .env files for backend, dashboard, and root
#
# Usage:
#   ./setup-gcp.sh                          # Interactive (prompts for project ID)
#   ./setup-gcp.sh <project-id>             # Non-interactive
#   ./setup-gcp.sh <project-id> <region>    # Custom region (default: us-central1)
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - Billing enabled on the GCP project
#   - Owner or Editor role on the project
#
# This script is IDEMPOTENT — safe to run multiple times.
# ============================================================================

set -euo pipefail

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()   { echo -e "${BLUE}[OMNI]${NC} $*"; }
ok()    { echo -e "${GREEN}  ✓${NC} $*"; }
warn()  { echo -e "${YELLOW}  ⚠${NC} $*"; }
err()   { echo -e "${RED}  ✗${NC} $*" >&2; }

# --- Configuration ---
PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null || echo '')}"
REGION="${2:-us-central1}"
SA_NAME="omni-backend"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET_NAME="${PROJECT_ID}-omni-artifacts"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SA_KEY_PATH="${REPO_ROOT}/backend/firebase-sa.json"

if [[ -z "$PROJECT_ID" ]]; then
  err "No project ID specified. Usage: ./setup-gcp.sh <project-id>"
  exit 1
fi

echo ""
log "============================================"
log "  Omni — GCP Infrastructure Setup"
log "============================================"
log "  Project:  ${PROJECT_ID}"
log "  Region:   ${REGION}"
log "  Bucket:   ${BUCKET_NAME}"
log "  SA:       ${SA_EMAIL}"
log "============================================"
echo ""

# --- Set Project ---
log "Setting active project..."
gcloud config set project "$PROJECT_ID" --quiet 2>/dev/null
ok "Project set to ${PROJECT_ID}"

# =============================================
# 1. Enable APIs
# =============================================
log "Enabling GCP APIs..."

APIS=(
  aiplatform.googleapis.com          # Vertex AI (Gemini, Imagen, RAG Engine)
  generativelanguage.googleapis.com  # Generative Language API
  firestore.googleapis.com           # Firestore
  firebase.googleapis.com            # Firebase Management
  identitytoolkit.googleapis.com     # Firebase Auth (Identity Toolkit)
  storage.googleapis.com             # Cloud Storage
  cloudbuild.googleapis.com          # Cloud Build (CI/CD)
  run.googleapis.com                 # Cloud Run
  secretmanager.googleapis.com       # Secret Manager
  iam.googleapis.com                 # IAM
  artifactregistry.googleapis.com    # Artifact Registry
  cloudtrace.googleapis.com          # Cloud Trace (observability)
  monitoring.googleapis.com          # Cloud Monitoring (observability)
  logging.googleapis.com             # Cloud Logging (observability)
)

gcloud services enable "${APIS[@]}" --quiet 2>&1
ok "Enabled ${#APIS[@]} APIs"

# =============================================
# 2. Firestore Database
# =============================================
log "Setting up Firestore..."

EXISTING_DB=$(gcloud firestore databases list --format="value(name)" 2>/dev/null || echo "")
if [[ -z "$EXISTING_DB" ]]; then
  gcloud firestore databases create \
    --location="$REGION" \
    --type=firestore-native \
    --quiet 2>&1
  ok "Created Firestore database (Native mode, ${REGION})"
else
  ok "Firestore database already exists"
fi

# =============================================
# 3. Cloud Storage Bucket
# =============================================
log "Setting up Cloud Storage..."

if gcloud storage buckets describe "gs://${BUCKET_NAME}" &>/dev/null; then
  ok "Bucket gs://${BUCKET_NAME} already exists"
else
  gcloud storage buckets create "gs://${BUCKET_NAME}" \
    --location="$REGION" \
    --uniform-bucket-level-access \
    --quiet 2>&1
  ok "Created bucket gs://${BUCKET_NAME}"
fi

# =============================================
# 4. Artifact Registry
# =============================================
log "Setting up Artifact Registry..."

if gcloud artifacts repositories describe omni --location="$REGION" &>/dev/null; then
  ok "Artifact Registry 'omni' already exists"
else
  gcloud artifacts repositories create omni \
    --location="$REGION" \
    --repository-format=docker \
    --description="Omni container images" \
    --quiet 2>&1
  ok "Created Artifact Registry 'omni'"
fi

# =============================================
# 5. Service Account
# =============================================
log "Setting up service account..."

if gcloud iam service-accounts describe "$SA_EMAIL" &>/dev/null; then
  ok "Service account ${SA_NAME} already exists"
else
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="Omni Backend Service Account" \
    --quiet 2>&1
  ok "Created service account ${SA_NAME}"
fi

# --- IAM Roles (least privilege) ---
log "Assigning IAM roles..."

ROLES=(
  roles/firebase.admin              # Firebase Admin SDK operations
  roles/datastore.user              # Firestore read/write
  roles/storage.objectAdmin         # GCS upload/download artifacts
  roles/aiplatform.user             # Vertex AI model inference
  roles/secretmanager.secretAccessor # Read secrets (E2B key, etc.)
)

for role in "${ROLES[@]}"; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$role" \
    --quiet --no-user-output-enabled 2>&1
  ok "Granted ${role}"
done

# --- Download Key ---
if [[ -f "$SA_KEY_PATH" ]]; then
  ok "Service account key already exists at ${SA_KEY_PATH}"
else
  gcloud iam service-accounts keys create "$SA_KEY_PATH" \
    --iam-account="$SA_EMAIL" \
    --quiet 2>&1
  ok "Downloaded SA key to ${SA_KEY_PATH}"
fi

# =============================================
# 6. Secret Manager
# =============================================
log "Setting up Secret Manager..."

if gcloud secrets describe e2b-api-key &>/dev/null; then
  ok "Secret 'e2b-api-key' already exists"
else
  gcloud secrets create e2b-api-key \
    --replication-policy=automatic \
    --quiet 2>&1
  ok "Created secret 'e2b-api-key'"
  warn "Add your E2B key: gcloud secrets versions add e2b-api-key --data-file=-"
fi

# =============================================
# 7. Populate .env Files
# =============================================
log "Populating environment files..."

# --- backend/.env ---
cat > "${REPO_ROOT}/backend/.env" << ENVEOF
# ======================================
# Omni Backend — Environment Variables
# ======================================
# Auto-generated by setup-gcp.sh

# --- Google Cloud / Vertex AI ---
GOOGLE_CLOUD_PROJECT=${PROJECT_ID}
GOOGLE_CLOUD_LOCATION=${REGION}
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_APPLICATION_CREDENTIALS=firebase-sa.json

# --- Firebase ---
FIREBASE_PROJECT_ID=${PROJECT_ID}
FIREBASE_SERVICE_ACCOUNT=firebase-sa.json

# --- E2B Sandbox ---
E2B_API_KEY=your-e2b-api-key

# --- Application ---
BACKEND_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
ENVIRONMENT=development

# --- GCS ---
GCS_BUCKET_NAME=${BUCKET_NAME}
ENVEOF
ok "Written backend/.env"

# --- root .env ---
cat > "${REPO_ROOT}/.env" << ENVEOF
# ======================================
# OMNI — Root Environment Variables
# ======================================
# Auto-generated by setup-gcp.sh

# --- Google Cloud ---
GOOGLE_CLOUD_PROJECT=${PROJECT_ID}
GOOGLE_CLOUD_LOCATION=${REGION}
GOOGLE_GENAI_USE_VERTEXAI=true

# --- Firebase ---
FIREBASE_PROJECT_ID=${PROJECT_ID}

# --- E2B Sandbox ---
E2B_API_KEY=your-e2b-api-key

# --- Application ---
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# --- GCS ---
GCS_BUCKET_NAME=${BUCKET_NAME}
ENVEOF
ok "Written .env (root)"

# --- dashboard/.env (auto-populated via Firebase REST API) ---
log "Fetching Firebase web app config..."

ACCESS_TOKEN=$(gcloud auth print-access-token 2>/dev/null || echo "")
FIREBASE_HEADERS=(-H "Authorization: Bearer ${ACCESS_TOKEN}" -H "x-goog-user-project: ${PROJECT_ID}")

if [[ -n "$ACCESS_TOKEN" ]]; then
  # Ensure Firebase is enabled on the GCP project
  FB_STATUS=$(curl -s "${FIREBASE_HEADERS[@]}" \
    "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}" 2>/dev/null | grep -c '"ACTIVE"' || echo "0")

  if [[ "$FB_STATUS" -eq 0 ]]; then
    log "Adding Firebase to GCP project..."
    curl -s -X POST "${FIREBASE_HEADERS[@]}" \
      -H "Content-Type: application/json" \
      "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}:addFirebase" \
      -d '{}' >/dev/null 2>&1
    sleep 12
    ok "Firebase added to project"
  else
    ok "Firebase already active"
  fi

  # Ensure a web app exists
  EXISTING_APP=$(curl -s "${FIREBASE_HEADERS[@]}" \
    "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}/webApps" 2>/dev/null)
  APP_ID=$(echo "$EXISTING_APP" | grep -o '"appId": "[^"]*"' | head -1 | cut -d'"' -f4)

  if [[ -z "$APP_ID" ]]; then
    log "Creating Firebase web app 'Omni Dashboard'..."
    curl -s -X POST "${FIREBASE_HEADERS[@]}" \
      -H "Content-Type: application/json" \
      "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}/webApps" \
      -d '{"displayName": "Omni Dashboard"}' >/dev/null 2>&1
    sleep 8
    EXISTING_APP=$(curl -s "${FIREBASE_HEADERS[@]}" \
      "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}/webApps" 2>/dev/null)
    APP_ID=$(echo "$EXISTING_APP" | grep -o '"appId": "[^"]*"' | head -1 | cut -d'"' -f4)
    ok "Created web app: ${APP_ID}"
  else
    ok "Web app already exists: ${APP_ID}"
  fi

  # Fetch web app config
  if [[ -n "$APP_ID" ]]; then
    FB_CONFIG=$(curl -s "${FIREBASE_HEADERS[@]}" \
      "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}/webApps/${APP_ID}/config" 2>/dev/null)
    FB_API_KEY=$(echo "$FB_CONFIG" | grep -o '"apiKey": "[^"]*"' | cut -d'"' -f4)
    FB_AUTH_DOMAIN=$(echo "$FB_CONFIG" | grep -o '"authDomain": "[^"]*"' | cut -d'"' -f4)
    FB_STORAGE_BUCKET=$(echo "$FB_CONFIG" | grep -o '"storageBucket": "[^"]*"' | cut -d'"' -f4)
    FB_MESSAGING_ID=$(echo "$FB_CONFIG" | grep -o '"messagingSenderId": "[^"]*"' | cut -d'"' -f4)
  fi
fi

# Write dashboard/.env
FB_API_KEY="${FB_API_KEY:-your-firebase-web-api-key}"
FB_AUTH_DOMAIN="${FB_AUTH_DOMAIN:-${PROJECT_ID}.firebaseapp.com}"
FB_STORAGE_BUCKET="${FB_STORAGE_BUCKET:-${PROJECT_ID}.firebasestorage.app}"
FB_MESSAGING_ID="${FB_MESSAGING_ID:-000000000000}"
APP_ID="${APP_ID:-1:000000000000:web:placeholder}"

cat > "${REPO_ROOT}/dashboard/.env" << ENVEOF
# ======================================
# Omni Dashboard — Environment Variables
# ======================================
# Auto-generated by setup-gcp.sh

VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
VITE_FIREBASE_API_KEY=${FB_API_KEY}
VITE_FIREBASE_AUTH_DOMAIN=${FB_AUTH_DOMAIN}
VITE_FIREBASE_PROJECT_ID=${PROJECT_ID}
VITE_FIREBASE_STORAGE_BUCKET=${FB_STORAGE_BUCKET}
VITE_FIREBASE_MESSAGING_SENDER_ID=${FB_MESSAGING_ID}
VITE_FIREBASE_APP_ID=${APP_ID}
ENVEOF
ok "Written dashboard/.env"

# =============================================
# 8. Terraform Variables
# =============================================
log "Writing Terraform variables..."

cat > "${REPO_ROOT}/deploy/terraform/terraform.tfvars" << ENVEOF
# Auto-generated by setup-gcp.sh
project_id  = "${PROJECT_ID}"
region      = "${REGION}"
environment = "dev"
ENVEOF
ok "Written deploy/terraform/terraform.tfvars"

# =============================================
# 9. Application Default Credentials Check
# =============================================
log "Checking Application Default Credentials..."

if gcloud auth application-default print-access-token &>/dev/null; then
  ok "ADC configured"
else
  warn "ADC not configured. For local Vertex AI access, run:"
  warn "  gcloud auth application-default login"
  warn "  (Or set GOOGLE_APPLICATION_CREDENTIALS to the SA key)"
fi

# =============================================
# Summary
# =============================================
echo ""
log "============================================"
log "  Setup Complete!"
log "============================================"
log ""
log "  GCP Resources Provisioned:"
ok "  ${#APIS[@]} APIs enabled"
ok "  Firestore (Native mode, ${REGION})"
ok "  GCS bucket: ${BUCKET_NAME}"
ok "  Artifact Registry: omni"
ok "  Service account: ${SA_EMAIL}"
ok "  Secret Manager: e2b-api-key"
log ""
log "  Files Written:"
ok "  backend/.env"
ok "  .env (root)"
ok "  dashboard/.env"
ok "  backend/firebase-sa.json"
ok "  deploy/terraform/terraform.tfvars"
log ""
log "  Remaining Manual Steps:"
warn "  1. Get E2B API key → backend/.env & .env"
warn "     https://e2b.dev/dashboard"
warn "  2. Enable Firebase Auth Google provider in Console"
warn "     https://console.firebase.google.com/project/${PROJECT_ID}/authentication/providers"
warn "  3. (Optional) gcloud auth application-default login"
log ""
log "  Start developing:"
log "    cd backend && uv run uvicorn app.main:app --reload"
log "    cd dashboard && npm run dev"
log ""
