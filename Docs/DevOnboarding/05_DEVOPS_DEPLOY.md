# Track 5: DevOps & Deployment Guide

> **Scope**: Set up local dev environments, Docker, GCP deployment, CI/CD.
> **Directory**: `deploy/`
> **Prerequisites**: Docker, GCP account (for cloud), Firebase project

---

## Deployment Overview

```
deploy/
├── docker-compose.yml          # Run everything in Docker locally
├── scripts/
│   ├── local/                  # LOCAL DEV (no GCP needed)
│   │   ├── setup-env.sh        # Install deps + create .env
│   │   └── start-dev.sh        # Start backend + dashboard
│   └── gcloud/                 # GCP / CLOUD (needs gcloud CLI)
│       ├── setup-gcp.sh        # Provision all GCP resources
│       ├── deploy.sh           # Build, push, deploy to Cloud Run
│       └── seed-data.sh        # Seed Firestore with sample data
├── terraform/                  # Infrastructure as Code
│   ├── main.tf                 # All GCP resources
│   ├── variables.tf            # Input variables
│   ├── outputs.tf              # Output values
│   └── terraform.tfvars        # Your project values
└── SETUP_GUIDE.md              # Detailed setup walkthrough
```

---

## Option A: Local Development (Quickest)

### Prerequisites

| Tool | Install |
|------|---------|
| Python 3.12+ | [python.org](https://www.python.org/downloads/) |
| Node.js 22+ | [nodejs.org](https://nodejs.org/) |
| uv | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| pnpm | `npm install -g pnpm` |

### One-command setup

```bash
# Install all dependencies (backend + dashboard)
bash deploy/scripts/local/setup-env.sh

# Edit .env with your credentials
cp .env.example .env
# Fill in GOOGLE_CLOUD_PROJECT, Firebase config, etc.

# Start both servers
bash deploy/scripts/local/start-dev.sh
```

### Manual setup

```bash
# Backend
cd backend
uv sync                     # Install Python deps
cp .env.example .env        # Edit with your values
uv run uvicorn app.main:app --reload --port 8000

# Dashboard (in another terminal)
cd dashboard
cp .env.example .env        # Edit with your values
pnpm install
pnpm dev                    # http://localhost:5173
```

---

## Option B: Docker Compose

Run everything (backend + dashboard + Firestore emulator) in containers:

```bash
# From project root
cp .env.example .env        # Edit with your values
docker compose -f deploy/docker-compose.yml up
```

Services:
- **Backend**: `http://localhost:8080`
- **Dashboard**: `http://localhost:5173`
- **Firestore Emulator**: `localhost:8086`

The compose file mounts `backend/app/` read-only for hot-reload during development.

---

## Option C: GCP Cloud Run Deployment

### Prerequisites

- GCP account with billing enabled
- `gcloud` CLI installed and authenticated
- Firebase project created

### Using deploy scripts

```bash
# 1. Provision GCP resources (Cloud Run, Artifact Registry, etc.)
bash deploy/scripts/gcloud/setup-gcp.sh

# 2. Build, push, and deploy
bash deploy/scripts/gcloud/deploy.sh

# 3. Seed Firestore with sample data
bash deploy/scripts/gcloud/seed-data.sh
```

### Using Terraform

```bash
cd deploy/terraform
terraform init
terraform plan
terraform apply
```

---

## Environment Variables Reference

### Backend (`backend/.env`)

```env
# --- Google Cloud / Vertex AI ---
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true
AGENT_ENGINE_NAME=omni-agent-engine
USE_AGENT_ENGINE_SESSIONS=true
USE_AGENT_ENGINE_MEMORY_BANK=true
USE_AGENT_ENGINE_CODE_EXECUTION=true
AGENT_ENGINE_SESSION_TTL=604800s
AGENT_ENGINE_SANDBOX_TTL=86400s

# Quick local dev (alternative to Vertex AI):
# GOOGLE_API_KEY=your-gemini-api-key

# --- Firebase ---
FIREBASE_PROJECT_ID=your-firebase-project-id
FIREBASE_SERVICE_ACCOUNT=path/to/service-account.json

# --- E2B Sandbox ---
E2B_API_KEY=your-e2b-api-key

# --- Models ---
LIVE_MODEL=gemini-live-2.5-flash-native-audio
TEXT_MODEL=gemini-2.5-flash

# --- Application ---
BACKEND_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
ENVIRONMENT=development

# --- GCS (Cloud Storage) ---
GCS_BUCKET_NAME=omni-artifacts
```

### Dashboard (`dashboard/.env`)

```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000

VITE_FIREBASE_API_KEY=your-firebase-web-api-key
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-firebase-project-id
VITE_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
VITE_FIREBASE_MESSAGING_SENDER_ID=123456789
VITE_FIREBASE_APP_ID=1:123456789:web:abcdef
```

---

## GCP Resources Required

| Resource | Purpose |
|----------|---------|
| Cloud Run | Host backend API container |
| Artifact Registry | Store Docker images |
| Firestore | Session persistence, user data |
| Firebase Auth | User authentication |
| Cloud Storage | Artifact storage (images, files) |
| Vertex AI | Gemini model access |
| Secret Manager | API keys and credentials |

---

## Firebase Setup

1. Go to [Firebase Console](https://console.firebase.google.com)
2. Create (or select) a project linked to your GCP project
3. Enable **Authentication** → **Email/password** and/or **Google sign-in**
4. Go to **Project Settings** → **Service accounts** → **Generate new private key**
5. Save the JSON file and set `FIREBASE_SERVICE_ACCOUNT` path in `.env`
6. For the dashboard: copy Web app config values into `dashboard/.env`

---

## Running Tests

```bash
cd backend
python -m pytest tests/ -v                    # All tests
python -m pytest tests/ -v --tb=short -q      # Concise output
python -m pytest tests/test_services/ -v       # Service tests only
```

### Current test suite: 54 tests passing

```
tests/test_services/test_tool_registry.py     — 38 tests (T1/T2/T3 + bug fixes)
tests/test_services/test_plugin_registry.py   — 16 tests (plugin lifecycle)
```

---

## Docker Images

### Backend Dockerfile (`backend/Dockerfile`)

- Base: Python 3.12 slim
- Package manager: `uv`
- Port: 8080 (in container), mapped to host

### Dashboard Dockerfile (`dashboard/Dockerfile`)

- Build stage: Node + pnpm → `dist/`
- Runtime: Nginx serving static files
- Port: 80 (in container), mapped to 5173 on host

---

## Health Check

The backend exposes a health endpoint:

```
GET /health
→ {"status": "ok"}
```

Docker Compose uses this for health checks with 15-second intervals.

---

## Logs & Monitoring

- **Local**: Logs print to stdout. Use `--log-level debug` for verbose output.
- **Cloud Run**: Logs appear in GCP Cloud Logging (structured JSON).
- **Firestore**: Check emulator UI at `http://localhost:8086` (Docker) or Firebase Console (production).

---

## CI/CD Recommendations

For hackathon rapid iteration:

```yaml
# Example GitHub Actions workflow
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Auth to GCP
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
      - name: Deploy
        run: bash deploy/scripts/gcloud/deploy.sh
```

---

## Common Issues

| Issue | Fix |
|-------|-----|
| `GOOGLE_CLOUD_PROJECT not set` | Set it in `.env` or export it before running |
| `Firebase auth fails locally` | Ensure `FIREBASE_SERVICE_ACCOUNT` points to valid JSON |
| `Port 8000 already in use` | Kill the process or change `BACKEND_PORT` |
| `uv not found` | Install: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `pnpm not found` | Install: `npm install -g pnpm` |
| `Docker build fails` | Ensure Docker Desktop is running with enough resources |
| `Firestore emulator OOM` | Increase Docker memory to 4GB+ |

---

## Quick Reference Commands

```bash
# Backend
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd backend && python -m pytest tests/ -v

# Dashboard
cd dashboard && pnpm dev
cd dashboard && pnpm build

# Docker
docker compose -f deploy/docker-compose.yml up
docker compose -f deploy/docker-compose.yml down

# GCP
bash deploy/scripts/gcloud/deploy.sh
gcloud run services list
gcloud run services logs read omni-backend
```
