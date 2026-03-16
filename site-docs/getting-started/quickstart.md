# Quick Start

Get Omni running locally in under 5 minutes.

## 1. Clone the Repository

```bash
git clone https://github.com/omanandswami2005/omni-agent-hub-with-gemini-live/
cd omni
```

## 2. Start the Backend

```bash
cd backend
uv sync
cp .env.example .env  # Fill in your credentials
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 3. Start the Dashboard

```bash
cd dashboard
pnpm install
pnpm dev
```

## 4. Open the Dashboard

Navigate to `http://localhost:5173` in your browser, sign in with Firebase Auth, and start talking to Omni.

## What You Can Do

- **Voice chat** — Click the microphone and speak naturally
- **Switch personas** — Try "Switch to coder" or "Switch to analyst"
- **Use plugins** — Enable Brave Search, Google Maps, or Zapier from the plugin store
- **Cloud desktop** — Say "Start a desktop" to spin up a virtual Linux desktop
- **GenUI** — Ask "Show me a chart of..." to see interactive visualizations
- **Cross-client** — Connect the desktop client and say "Type hello on my desktop"

## Troubleshooting

!!! tip "Common issues"

    - **Audio not working?** — Make sure your browser allows microphone access
    - **Backend connection failed?** — Check that the backend is running on port 8000
    - **Firebase auth error?** — Verify your Firebase API key in the `.env` files
