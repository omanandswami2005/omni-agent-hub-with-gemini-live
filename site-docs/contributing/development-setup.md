# Development Setup

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12+ | [python.org](https://www.python.org/) |
| Node.js | 20+ | [nodejs.org](https://nodejs.org/) |
| pnpm | 9+ | `npm install -g pnpm` |
| uv | latest | `pip install uv` |

## Backend

```bash
cd backend
uv sync
uvicorn app.main:app --reload
```

## Dashboard

```bash
cd dashboard
pnpm install
pnpm dev
```

## Desktop Client

```bash
cd desktop-client
uv sync
uv run omni-desktop connect
```

## Running Tests

### Backend

```bash
cd backend
uv run pytest
```

### Dashboard

```bash
cd dashboard
pnpm run lint
```

## Linting

```bash
# Python
cd backend && uv tool run ruff check .

# JavaScript
cd dashboard && pnpm run lint
```
