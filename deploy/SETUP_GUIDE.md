# Omni — Setup & Deployment Guide

> Quick-start guide. Covers local dev, GCP provisioning, and production deployment.

---

## Directory Structure

```
deploy/
├── scripts/
│   ├── local/
│   │   ├── setup-env.sh        # Install deps + create .env
│   │   └── start-dev.sh        # Start backend + dashboard locally
│   └── gcloud/
│       ├── setup-gcp.sh        # Provision all GCP resources (first time)
│       ├── deploy-all.sh       # Build + deploy backend + dashboard
│       ├── seed-data.sh        # Seed Firestore with default data
│       └── fresh-start.sh      # Wipe all data (keep infrastructure)
```

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

# 2. Edit .env with your credentials
#    At minimum: GOOGLE_CLOUD_PROJECT, Firebase config, E2B_API_KEY

# 3. Start both servers
bash deploy/scripts/local/start-dev.sh
#    → Backend:   http://localhost:8000
#    → Dashboard: http://localhost:5173
```

---

## Option B: GCP Cloud Deployment

### Prerequisites

| Tool | Install |
|------|---------|
| **gcloud CLI** | [cloud.google.com/sdk](https://cloud.google.com/sdk/docs/install) |
| **Docker** | [docker.com](https://www.docker.com/) |
| **firebase CLI** | `npm install -g firebase-tools` |
| **pnpm** | `npm install -g pnpm` |

### First-Time Setup

```bash
# 1. Authenticate
gcloud auth login
gcloud auth application-default login
firebase login

# 2. Provision ALL GCP infrastructure
bash deploy/scripts/gcloud/setup-gcp.sh <your-project-id>
#    → Enables 14 GCP APIs, Firestore, GCS bucket, Artifact Registry,
#      service account + IAM, Firebase web app, writes all .env files

# 3. Seed Firestore with default personas + MCP catalog
bash deploy/scripts/gcloud/seed-data.sh <your-project-id>

# 4. Build + deploy everything
bash deploy/scripts/gcloud/deploy-all.sh <your-project-id>
#    → Backend  → Cloud Run (Docker → Artifact Registry → Cloud Run)
#    → Dashboard → Firebase Hosting (pnpm build → firebase deploy)
```

### Subsequent Deployments

```bash
# Deploy everything
bash deploy/scripts/gcloud/deploy-all.sh

# Backend only
SKIP_DASHBOARD=1 bash deploy/scripts/gcloud/deploy-all.sh

# Dashboard only
SKIP_BACKEND=1 bash deploy/scripts/gcloud/deploy-all.sh

# Re-deploy existing image (no Docker build)
SKIP_BUILD=1 bash deploy/scripts/gcloud/deploy-all.sh
```

### Fresh Start (Wipe Data)

```bash
# Preview what would be deleted
DRY_RUN=1 bash deploy/scripts/gcloud/fresh-start.sh

# Execute cleanup
bash deploy/scripts/gcloud/fresh-start.sh
```

---

## Script Reference

### Local Scripts

| Script | Purpose | When |
|--------|---------|------|
| `local/setup-env.sh` | Install Python + Node deps, create .env | Once |
| `local/start-dev.sh` | Start backend (:8000) + dashboard (:5173) | Daily |

### GCloud Scripts

| Script | Purpose | When |
|--------|---------|------|
| `gcloud/setup-gcp.sh` | Provision all GCP resources (14 APIs, Firestore, GCS, IAM, Firebase) | Once |
| `gcloud/deploy-all.sh` | Build + deploy backend (Cloud Run) + dashboard (Firebase Hosting) | Each deploy |
| `gcloud/seed-data.sh` | Seed Firestore with 5 personas + MCP catalog | Once / after reset |
| `gcloud/fresh-start.sh` | Wipe all data — Cloud Run revisions, GCS, Firestore, Vertex AI engines | When needed |

---

## Execution Order

```
First Time:
  1. setup-env.sh       ← Install deps
  2. setup-gcp.sh       ← Provision GCP
  3. seed-data.sh       ← Seed database
  4. deploy-all.sh      ← Deploy to cloud

Daily Dev:
  1. start-dev.sh       ← Start local servers

Deploying:
  1. deploy-all.sh      ← Build + deploy
```
