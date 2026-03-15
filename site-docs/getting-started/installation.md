# Installation

## Backend

=== "Using uv (recommended)"

    ```bash
    cd backend
    uv sync
    ```

=== "Using pip"

    ```bash
    cd backend
    pip install -e .
    ```

### Environment Variables

Create a `.env` file in `backend/`:

```env
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
E2B_API_KEY=your-e2b-api-key
FIREBASE_SA_PATH=firebase-sa.json
```

### Run the Backend

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API docs will be available at `http://localhost:8000/docs`.

## Dashboard

```bash
cd dashboard
pnpm install
pnpm dev
```

The dashboard will be available at `http://localhost:5173`.

### Environment Variables

Create a `.env` file in `dashboard/`:

```env
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
VITE_FIREBASE_API_KEY=your-firebase-api-key
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project-id
```

## Desktop Client

```bash
cd desktop-client
uv sync
uv run omni-desktop connect
```

## Chrome Extension

1. Open `chrome://extensions/` in Chrome
2. Enable **Developer mode**
3. Click **Load unpacked** and select the `chrome-extension/` directory

## CLI

```bash
cd cli
python omni_cli.py
```
