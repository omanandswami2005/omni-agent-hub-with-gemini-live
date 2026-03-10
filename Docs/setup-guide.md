# Setup Guide

## Prerequisites

- **Python 3.12+** with [uv](https://docs.astral.sh/uv/) package manager
- **Node.js 20+** with npm
- **Google Cloud** project with Vertex AI enabled
- **Firebase** project (Authentication + Firestore)
- **E2B** account for sandbox code execution

## Quick Start

### 1. Clone & Configure

```bash
git clone <repo-url>
cd agent-hub

# Copy environment templates
cp .env.example .env
cp backend/.env.example backend/.env
cp dashboard/.env.example dashboard/.env

# Edit each .env with your actual values
```

### 2. Backend

```bash
cd backend
uv sync                                    # Install dependencies
uv run uvicorn app.main:app --reload       # Start at http://localhost:8000
```

### 3. Dashboard

```bash
cd dashboard
npm install                                # Install dependencies
npm run dev                                # Start at http://localhost:5173
```

### 4. Desktop Client (Optional)

```bash
cd desktop-client
uv sync
uv run python src/main.py connect
```

### 5. Chrome Extension (Optional)

1. Open `chrome://extensions/`
2. Enable "Developer mode"
3. Click "Load unpacked" → select `chrome-extension/` folder

## Code Quality

```bash
# Backend linting & formatting
cd backend
uv run ruff check app/                     # Lint
uv run ruff format app/                    # Format
uv run pytest                              # Tests

# Dashboard linting & formatting
cd dashboard
npx eslint src/ --fix                      # Lint
npx prettier --write src/                  # Format
```

## Project Structure

See [PROJECT_STRUCTURE_AND_UI_SPECS.md](../Docs/PROJECT_STRUCTURE_AND_UI_SPECS.md) for the complete folder layout and UI specifications.
