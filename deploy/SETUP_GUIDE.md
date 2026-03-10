# Omni — Setup & Deployment Guide

> Quick-start guide for developers. Covers local dev setup, GCP provisioning, and deployment.

---

## Directory Structure

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
│   └── terraform.tfvars        # Your project values (auto-generated)
```

**Root-level config files:**

| File | Purpose |
|------|---------|
| `.env` / `.env.example` | Environment variables (API keys, project IDs) |
| `firebase.json` | Firebase Hosting config + Firestore indexes path |
| `firestore.indexes.json` | Composite Firestore indexes for query performance |
| `backend/Dockerfile` | Backend container image (Python + FastAPI) |
| `dashboard/Dockerfile` | Dashboard container image (Vite build → Nginx) |

---

## Option A: Local Development (Quickest)

### Prerequisites

| Tool | Install |
|------|---------|
| **Python 3.12+** | [python.org](https://www.python.org/downloads/) |
| **Node.js 22+** | [nodejs.org](https://nodejs.org/) |
| **uv** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **pnpm** | `npm install -g pnpm` |

### Steps

```bash
# 1. Install all dependencies (backend + dashboard + desktop-client)
bash deploy/scripts/local/setup-env.sh

# 2. Edit .env with your credentials (see "What You Need" below)
#    At minimum: GOOGLE_CLOUD_PROJECT, Firebase config, E2B_API_KEY

# 3. Start both servers
bash deploy/scripts/local/start-dev.sh
#    → Backend:   http://localhost:8000
#    → Dashboard: http://localhost:5173
```

---

## Option B: Docker Compose (Full Stack Local)

### Prerequisites

- Docker Desktop installed and running

### Steps

```bash
# 1. Copy environment file
cp .env.example .env
# Edit .env with your values

# 2. Start everything (backend + dashboard + Firestore emulator)
cd deploy && docker compose up --build

#    → Backend:    http://localhost:8080
#    → Dashboard:  http://localhost:5173
#    → Firestore:  localhost:8086 (emulator, no GCP needed)
```

> **Note:** Docker Compose mode uses the Firestore emulator — no GCP project required for basic testing.

---

## Option C: GCP Cloud Deployment

### Prerequisites

| Tool | Install |
|------|---------|
| **gcloud CLI** | [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) |
| **Terraform 1.5+** | [terraform.io](https://developer.hashicorp.com/terraform/install) |
| **Docker** | [docker.com](https://www.docker.com/) |

### Execution Sequence

```bash
# 1. Authenticate with GCP
gcloud auth login
gcloud auth application-default login

# 2. Provision ALL GCP infrastructure (APIs, Firestore, Storage, IAM, Firebase)
bash deploy/scripts/gcloud/setup-gcp.sh <your-project-id>
#    This also auto-generates: .env, backend/.env, dashboard/.env, terraform.tfvars

# 3. Seed Firestore with default personas and MCP catalog
bash deploy/scripts/gcloud/seed-data.sh <your-project-id>

# 4. Build & deploy to Cloud Run
bash deploy/scripts/gcloud/deploy.sh <your-project-id>
#    Builds Docker image → pushes to Artifact Registry → runs Terraform → deploys
```

### Deployment Modes

```bash
# Skip docker build, only run Terraform
SKIP_BUILD=1 bash deploy/scripts/gcloud/deploy.sh

# Skip Terraform, only deploy via gcloud run deploy
SKIP_TF=1 bash deploy/scripts/gcloud/deploy.sh
```

---

## Script Details

### Local Scripts

| Script | What It Does | When to Run |
|--------|-------------|-------------|
| `local/setup-env.sh` | Installs Python deps (uv sync), Node deps (pnpm install), copies .env.example → .env | **Once**, first time setup |
| `local/start-dev.sh` | Starts backend (uvicorn :8000) + dashboard (vite :5173) in parallel | **Every time** you develop |

### GCloud Scripts

| Script | What It Does | When to Run |
|--------|-------------|-------------|
| `gcloud/setup-gcp.sh` | Enables 14 GCP APIs, creates Firestore DB, GCS bucket, Artifact Registry, service account (5 IAM roles), downloads SA key, creates Firebase web app, writes all .env files | **Once**, initial GCP setup |
| `gcloud/deploy.sh` | Builds backend Docker image, pushes to Artifact Registry, runs Terraform apply, deploys to Cloud Run | **Every deployment** |
| `gcloud/seed-data.sh` | Seeds Firestore with 5 default personas + 5 MCP catalog entries | **Once**, or after DB reset |

### Terraform

| File | Purpose |
|------|---------|
| `main.tf` | Defines: Cloud Run, Firestore, GCS, Artifact Registry, Secret Manager, Service Account (7 IAM bindings), Firebase Hosting, Monitoring alerts |
| `variables.tf` | Inputs: project_id, region, environment, image_tag, domain |
| `outputs.tf` | Outputs: backend_url, artifact_registry, storage_bucket, hosting_url |
| `terraform.tfvars` | Your values (auto-generated by setup-gcp.sh) |

---

## Execution Order Summary

```
First Time (complete):
  1. setup-env.sh          ← Install deps, create .env
  2. Edit .env             ← Add credentials
  3. setup-gcp.sh          ← Provision GCP (if using cloud)
  4. seed-data.sh          ← Seed database
  5. start-dev.sh          ← Start developing

Daily Development:
  1. start-dev.sh          ← That's it

Deploying to Cloud:
  1. deploy.sh             ← Build + push + terraform + deploy
```
