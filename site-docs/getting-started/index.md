# Getting Started

Welcome to the Omni documentation. This guide will help you set up and run the entire Omni stack locally.

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Backend, desktop client |
| Node.js | 20+ | Dashboard |
| pnpm | 9+ | Dashboard package manager |
| uv | latest | Python package manager |
| Docker | latest | Optional — containerized deployment |
| GCP Account | — | Gemini API, Firebase, Cloud Run |

## Project Components

Omni is composed of several interconnected components:

```
omni/
├── backend/          # FastAPI server + ADK agents
├── dashboard/        # React 19 + Vite 6 web app
├── desktop-client/   # PyQt6 desktop agent
├── chrome-extension/ # Browser control extension
├── smart-glasses/    # ESP32 wearable client
├── cli/              # Terminal client
├── deploy/           # Terraform, Docker, scripts
└── docs/             # This documentation
```

## Next Steps

- [Installation](installation.md) — Set up each component
- [Quick Start](quickstart.md) — Get a working demo in minutes
- [Architecture Overview](../architecture/index.md) — Understand the system design
