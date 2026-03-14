# Omni — Architecture & Deployment Reference

> Multi-client AI agent hub powered by Gemini Live on Google Cloud.

---

## GCP Services Used

| Service | Role |
|---------|------|
| **Cloud Run** | Backend API (FastAPI + WebSocket). Containerized, auto-scales 0→10 instances. Session affinity for persistent WS connections. |
| **Firebase Hosting** | Dashboard SPA (React + Vite). Global CDN, instant cache invalidation. |
| **Firebase Auth** | Google sign-in. JWT validated on every API request and WS upgrade. |
| **Firestore** | NoSQL database — sessions, personas, memories, client presence, MCP configs. |
| **Cloud Storage (GCS)** | File uploads, generated images, code sandbox artifacts. |
| **Vertex AI** | Gemini Live 2.5 Flash (native audio) for real-time voice, Gemini 2.5 Flash for text, Imagen for image gen. |
| **Artifact Registry** | Docker container images for backend. |
| **Secret Manager** | API keys (E2B sandbox key). |

---

## GCP Console — Where to Find Each Service

All services live at [console.cloud.google.com](https://console.cloud.google.com). Select your project from the top dropdown.

### Cloud Run (Backend)
```
☰ Menu → Cloud Run → Services → omni-backend
```
- **Revisions** tab: see all deployed versions, traffic splitting
- **Logs** tab: real-time backend logs (errors, requests)
- **Metrics** tab: request count, latency, instance count
- **YAML** tab: full service config (env vars, scaling, etc.)
- **Networking** tab: session affinity, ingress settings

### Firebase Hosting (Dashboard)
```
☰ Menu → Firebase Console (console.firebase.google.com)
  → Your Project → Hosting
```
- Shows release history, active version, storage usage
- Or via GCP: `☰ → Firebase Hosting` in GCP Console sidebar

### Firebase Auth (Users)
```
Firebase Console → Authentication → Users
```
- See all registered users, sign-in providers, last login
- **Sign-in method** tab: enable/disable Google, email, etc.
- **Settings** tab: authorized domains (add your `.web.app` domain here)

### Firestore (Database)
```
☰ Menu → Firestore → Data
```
- Browse collections: `sessions`, `personas`, `memories`, `client_presence`
- Click any document to inspect fields
- **Indexes** tab: composite indexes for query performance
- **Rules** tab: security rules (who can read/write)

### Cloud Storage (Files)
```
☰ Menu → Cloud Storage → Buckets → <project-id>-omni-artifacts
```
- Browse uploaded files, generated images
- **Permissions** tab: IAM for bucket access
- **Lifecycle** tab: auto-delete rules (optional)

### Vertex AI (Models)
```
☰ Menu → Vertex AI → Overview
```
- **Model Garden**: browse available Gemini models
- **Reasoning Engines**: `☰ → Vertex AI → Reasoning Engines` — agent sessions created by the app
- **APIs & Services → Enabled APIs**: confirm `aiplatform.googleapis.com` is enabled

### Artifact Registry (Container Images)
```
☰ Menu → Artifact Registry → Repositories → omni
```
- See all pushed Docker images + tags
- Click an image to see layers, vulnerabilities, digest

### Secret Manager (API Keys)
```
☰ Menu → Secret Manager → e2b-api-key
```
- See versions, enable/disable/destroy old versions
- **+ New Version**: rotate a secret

### OAuth 2.0 Credentials (Plugin OAuth)
```
☰ Menu → APIs & Services → Credentials
```
- **OAuth 2.0 Client IDs**: see `omni-backend` client
- Click it to edit **Authorized redirect URIs**:
  - Local: `http://localhost:8000/api/v1/plugins/google-oauth/callback`
  - Production: `https://<cloud-run-url>/api/v1/plugins/google-oauth/callback`
  - MCP OAuth: `http://localhost:8000/api/v1/plugins/oauth/callback` (local) / `https://<cloud-run-url>/api/v1/plugins/oauth/callback` (prod)
- **Authorized JavaScript origins**: add `https://<project-id>.web.app`

### IAM & Admin (Service Accounts)
```
☰ Menu → IAM & Admin → Service Accounts → omni-backend@<project-id>.iam.gserviceaccount.com
```
- See assigned roles: `datastore.user`, `storage.objectAdmin`, `aiplatform.user`, `secretmanager.secretAccessor`, `firebase.admin`
- **Keys** tab: manage service account JSON keys

### Monitoring & Logging
```
☰ Menu → Logging → Logs Explorer
```
- Filter: `resource.type="cloud_run_revision"` to see backend logs
- Or: `☰ → Monitoring → Dashboards` for metrics

---

## Persistence

| Data | Storage | Lifetime |
|------|---------|----------|
| User accounts | Firebase Auth | Permanent |
| Chat sessions (messages, metadata) | Firestore `sessions` collection | Until user deletes |
| Personas (AI personalities) | Firestore `personas` collection | Until user deletes |
| Cross-session memory (agent memory) | Firestore `memories` collection | Until user/agent deletes |
| Client presence (which devices online) | Firestore `client_presence` collection | Ephemeral (auto-expires) |
| Uploaded files / generated images | GCS bucket | Until user deletes |
| Live audio/video streams | In-memory only (WebSocket) | Not persisted |

---

## Multi-User & Multi-Session

- **Multi-user**: Firebase Auth isolates each user's data. Firestore security rules + backend JWT validation ensure user A cannot access user B's sessions/personas/files.
- **Multi-session**: Each user can have unlimited named sessions (chat threads). Sessions are stored in Firestore with full message history. Switching sessions is instant — no data loss.
- **Concurrent sessions**: Multiple sessions can exist, but only one live audio/video session is active at a time per user (hardware constraint — one mic/speaker).

---

## Cross-Client Architecture

Omni supports simultaneous connections from multiple client types per user:

| Client | Type | Capabilities |
|--------|------|-------------|
| **Dashboard** (web) | Full-featured — text, voice, vision, personas, MCP, settings |
| **Desktop Client** (Python) | Screen capture, system actions, voice — headless or windowed |
| **Chrome Extension** | Browser context injection, page summarization, voice from any tab |
| **Smart Glasses** (ESP32) | Always-on voice + camera, UDP audio bridge |
| **CLI** | Terminal-based text + voice agent access |

### How cross-client works:

1. All clients connect via WebSocket to the same backend session.
2. Messages from any client are broadcast to all other connected clients of that user.
3. **Mic floor**: Only one client can hold the mic at a time. `acquireMic()` / `releaseMic()` coordinate who speaks.
4. **Session transfer**: Starting a live session on one device automatically notifies other devices (via `session_suggestion` WS message).
5. Client presence is tracked in Firestore — the dashboard shows which devices are online.

---

## First-Time Deployment

### Prerequisites

- GCP project with billing enabled
- `gcloud` CLI, Docker, `firebase` CLI, `pnpm`, `uv`

### Steps

```bash
# 1. Authenticate
gcloud auth login && gcloud auth application-default login && firebase login

# 2. Provision infrastructure (APIs, Firestore, GCS, SA, Firebase)
bash deploy/scripts/gcloud/setup-gcp.sh <project-id>

# 3. Set your E2B API key (for code sandbox)
echo -n "YOUR_E2B_KEY" | gcloud secrets versions add e2b-api-key --data-file=-

# 4. Seed default personas + MCP catalog
bash deploy/scripts/gcloud/seed-data.sh <project-id>

# 5. Build and deploy
bash deploy/scripts/gcloud/deploy-all.sh <project-id>
```

After deployment:
- Backend: `https://omni-backend-XXXX.a.run.app` (Cloud Run)
- Dashboard: `https://<project-id>.web.app` (Firebase Hosting)

### What `setup-gcp.sh` provisions:

1. Enables 14 GCP APIs (Vertex AI, Firestore, Firebase, GCS, Cloud Run, Secret Manager, etc.)
2. Creates Firestore database (Native mode)
3. Creates GCS bucket (`<project-id>-omni-artifacts`)
4. Creates Artifact Registry repo (`omni`)
5. Creates service account (`omni-backend`) with 5 IAM roles
6. Downloads SA key for local dev
7. Creates Firebase web app + fetches config
8. Writes `backend/.env`, `dashboard/.env`, `.env`

---

## Subsequent Deployments

```bash
# Full deploy (backend + dashboard)
bash deploy/scripts/gcloud/deploy-all.sh

# Backend only
SKIP_DASHBOARD=1 bash deploy/scripts/gcloud/deploy-all.sh

# Dashboard only
SKIP_BACKEND=1 bash deploy/scripts/gcloud/deploy-all.sh

# Skip Docker build, just redeploy existing image
SKIP_BUILD=1 bash deploy/scripts/gcloud/deploy-all.sh
```

---

## Fresh Start (Data Reset)

Wipes all user data while keeping infrastructure intact. App remains fully functional — just empty.

```bash
# Preview
DRY_RUN=1 bash deploy/scripts/gcloud/fresh-start.sh

# Execute
bash deploy/scripts/gcloud/fresh-start.sh
```

**What gets wiped**: Old Cloud Run revisions, GCS bucket contents, all Firestore collections, Vertex AI reasoning engines, old Artifact Registry images.

**What stays**: Cloud Run service, Firebase Auth users, Firebase Hosting, GCS buckets (structure), Secret Manager secrets, all enabled APIs.

After fresh start, run `seed-data.sh` to re-create default personas.

---

## Configuration Files

| File | Purpose |
|------|---------|
| `backend/.env` | Backend local config (GCP project, model names, E2B key, OAuth) |
| `backend/cloud-run-env.yaml` | Production env vars for Cloud Run deploy |
| `dashboard/.env` | Dashboard config (API URL, Firebase keys) |
| `firebase.json` | Firebase Hosting config (serves `dashboard/dist`) |
| `firestore.indexes.json` | Composite Firestore indexes |

---

## Deployment Scripts

```
deploy/scripts/
├── local/
│   ├── setup-env.sh        # Install all deps (uv, pnpm)
│   └── start-dev.sh        # Start backend + dashboard locally
└── gcloud/
    ├── setup-gcp.sh        # First-time GCP provisioning
    ├── deploy-all.sh       # Build + deploy (Cloud Run + Firebase Hosting)
    ├── seed-data.sh        # Seed Firestore with defaults
    └── fresh-start.sh      # Wipe all data, keep infrastructure
```
