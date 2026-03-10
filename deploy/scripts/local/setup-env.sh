#!/usr/bin/env bash
# Set up local development environment.
#
# Usage: ./setup-env.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/../../.."

echo "=== Setting up Omni development environment ==="

# Backend
echo "--- Backend (Python) ---"
cd "${ROOT_DIR}/backend"
if command -v uv &> /dev/null; then
  uv sync
else
  echo "Install uv first: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

# Dashboard
echo "--- Dashboard (Node.js) ---"
cd "${ROOT_DIR}/dashboard"
if command -v pnpm &> /dev/null; then
  pnpm install
else
  echo "Install pnpm first: npm install -g pnpm"
  exit 1
fi

# Desktop client
echo "--- Desktop Client (Python) ---"
cd "${ROOT_DIR}/desktop-client"
uv sync

# Environment file
if [ ! -f "${ROOT_DIR}/.env" ]; then
  echo "--- Creating .env from .env.example ---"
  cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
  echo "⚠️  Edit .env with your actual values"
fi

echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Edit .env with your GCP project, Firebase, and E2B keys"
echo "  2. cd backend && uv run uvicorn app.main:app --reload"
echo "  3. cd dashboard && pnpm run dev"
