#!/usr/bin/env bash
# Set up local development environment.
#
# Usage: ./setup-env.sh

set -euo pipefail

echo "=== Setting up Omni development environment ==="

# Backend
echo "--- Backend (Python) ---"
cd ../backend
if command -v uv &> /dev/null; then
  uv sync
else
  echo "Install uv first: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
cd ..

# Dashboard
echo "--- Dashboard (Node.js) ---"
cd ../dashboard
npm install
cd ..

# Desktop client
echo "--- Desktop Client (Python) ---"
cd ../desktop-client
uv sync
cd ..

# Environment file
if [ ! -f ../.env ]; then
  echo "--- Creating .env from .env.example ---"
  cp ../.env.example ../.env
  echo "⚠️  Edit .env with your actual values"
fi

echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Edit .env with your GCP project, Firebase, and E2B keys"
echo "  2. cd backend && uv run uvicorn app.main:app --reload"
echo "  3. cd dashboard && npm run dev"
