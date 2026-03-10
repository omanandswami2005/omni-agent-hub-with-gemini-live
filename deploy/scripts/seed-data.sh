#!/usr/bin/env bash
# Seed Firestore with initial data (default personas, MCP servers).
#
# Usage: ./seed-data.sh [project-id]

set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project)}"

echo "=== Seeding Firestore for project: ${PROJECT_ID} ==="

# TODO: Use Firebase Admin SDK or gcloud CLI to seed:
#   - Default personas (General Assistant, Code Architect, Research Analyst, etc.)
#   - Curated MCP server catalog
#   - Sample session for demo

echo "⚠️  Seed script not yet implemented — add persona and MCP data to Firestore manually or via the dashboard UI."
