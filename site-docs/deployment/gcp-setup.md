# GCP Setup

Deploy Omni to Google Cloud Platform.

## Prerequisites

- GCP project with billing enabled
- `gcloud` CLI installed and authenticated
- Firebase project linked to your GCP project
- E2B API key

## Required APIs

Enable these APIs in your GCP project:

```bash
gcloud services enable \
  run.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  cloudbuild.googleapis.com
```

## Backend Deployment (Cloud Run)

```bash
gcloud run deploy omni-backend \
  --source backend \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --min-instances 0 \
  --max-instances 3 \
  --timeout 300
```

## Dashboard Deployment (Firebase Hosting)

```bash
cd dashboard
pnpm run build
npx firebase-tools deploy --only hosting --project your-project-id
```

## Environment Variables

Set these in Cloud Run:

| Variable | Description |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | Region (e.g., `us-central1`) |
| `E2B_API_KEY` | E2B sandbox API key |
| `FIREBASE_SA_PATH` | Path to Firebase service account JSON |
