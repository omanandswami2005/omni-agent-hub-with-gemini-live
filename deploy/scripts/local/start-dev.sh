#!/usr/bin/env bash
# Start local development servers (backend + dashboard).
#
# Usage: ./start-dev.sh
#
# Starts backend API (port 8000) and dashboard (port 5173) in parallel.
# Press Ctrl+C to stop both.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/../../.."

# Check dependencies
if ! command -v uv &>/dev/null; then
  echo "Error: uv not installed. Run: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
if ! command -v pnpm &>/dev/null; then
  echo "Error: pnpm not installed. Run: npm install -g pnpm"
  exit 1
fi

# Check .env
if [ ! -f "${ROOT_DIR}/.env" ]; then
  echo "Error: .env not found. Run setup-env.sh first."
  exit 1
fi

trap 'kill 0' EXIT

echo "=== Starting Omni (local dev) ==="

# Backend
echo "--- Starting backend (port 8000) ---"
cd "${ROOT_DIR}/backend"
uv run python dev.py &

# Dashboard
echo "--- Starting dashboard (port 5173) ---"
cd "${ROOT_DIR}/dashboard"
pnpm run dev &

echo ""
echo "=== Omni running ==="
echo "  Backend:   http://localhost:8000"
echo "  Dashboard: http://localhost:5173"
echo "  Press Ctrl+C to stop"
echo ""

wait
