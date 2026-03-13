#!/usr/bin/env bash
# Seed Firestore with initial data (default personas, MCP servers).
#
# Usage: ./seed-data.sh [project-id]
#
# Requires: gcloud CLI with Firestore access.
# Seeds data via a small Python script using firebase-admin.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/../../.."
PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"

echo "=== Seeding Firestore for project: ${PROJECT_ID} ==="

# Run the seed script using the backend's Python environment
cd "${ROOT_DIR}/backend"

uv run python -c "
import os
os.environ.setdefault('GOOGLE_CLOUD_PROJECT', '${PROJECT_ID}')

import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
if not firebase_admin._apps:
    try:
        cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)
    except Exception:
        firebase_admin.initialize_app()

db = firestore.client()

# --- Default Personas ---
personas = [
    {
        'name': 'General Assistant',
        'avatar': '',
        'system_instruction': 'You are a helpful, concise AI assistant. Answer questions clearly and accurately.',
        'voice': 'Puck',
        'mcp_servers': [],
        'is_default': True,
    },
    {
        'name': 'Code Architect',
        'avatar': '',
        'system_instruction': 'You are an expert software architect. Help with code design, debugging, architecture decisions, and implementation. Always consider scalability, security, and maintainability.',
        'voice': 'Fenrir',
        'mcp_servers': [],
        'is_default': False,
    },
    {
        'name': 'Research Analyst',
        'avatar': '',
        'system_instruction': 'You are a research analyst. Help users find information, analyze data, summarize documents, and provide well-sourced insights. Use search tools when available.',
        'voice': 'Aoede',
        'mcp_servers': [],
        'is_default': False,
    },
    {
        'name': 'Creative Writer',
        'avatar': '',
        'system_instruction': 'You are a creative writing assistant. Help with storytelling, poetry, marketing copy, blog posts, and any creative text. Be imaginative and engaging.',
        'voice': 'Kore',
        'mcp_servers': [],
        'is_default': False,
    },
    {
        'name': 'Data Scientist',
        'avatar': '',
        'system_instruction': 'You are a data science expert. Help with data analysis, visualization, ML concepts, statistics, and Python data tools (pandas, numpy, matplotlib, scikit-learn). Use code execution when available.',
        'voice': 'Charon',
        'mcp_servers': [],
        'is_default': False,
    },
]

print('Seeding personas...')
for p in personas:
    doc_ref = db.collection('personas').document()
    doc_ref.set(p)
    print(f'  ✓ {p[\"name\"]}')

# --- Curated MCP Server Catalog ---
# Matches the 9 MCP server configs in backend/app/mcps/*.json
mcp_catalog = [
    {
        'id': 'brave-search',
        'name': 'Brave Search',
        'description': 'Web search via the Brave Search API.',
        'icon': 'brave',
        'category': 'search',
        'kind': 'mcp_stdio',
        'command': 'npx',
        'args': ['-y', '@anthropic/mcp-brave-search'],
        'requires_auth': True,
        'env_keys': ['BRAVE_API_KEY'],
        'tags': ['search', 'web'],
    },
    {
        'id': 'cloud-sql',
        'name': 'Cloud SQL',
        'description': 'Query Google Cloud SQL databases — PostgreSQL, MySQL, SQL Server.',
        'icon': 'cloud-sql',
        'category': 'data',
        'kind': 'mcp_stdio',
        'command': 'npx',
        'args': ['-y', '@anthropic/mcp-server-postgres'],
        'requires_auth': True,
        'env_keys': ['CLOUD_SQL_CONNECTION_STRING'],
        'tags': ['data', 'gcp', 'sql'],
    },
    {
        'id': 'e2b-sandbox',
        'name': 'E2B Sandbox',
        'description': 'Sandboxed code execution — run Python, Node.js, shell commands with full file system.',
        'icon': 'sandbox',
        'category': 'sandbox',
        'kind': 'e2b',
        'tags': ['code_execution', 'sandbox'],
    },
    {
        'id': 'filesystem',
        'name': 'Filesystem',
        'description': 'Read/write files in a sandboxed directory.',
        'icon': 'folder',
        'category': 'other',
        'kind': 'mcp_stdio',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-filesystem'],
        'tags': ['code_execution', 'sandbox'],
    },
    {
        'id': 'github',
        'name': 'GitHub',
        'description': 'Interact with GitHub repos, issues, PRs.',
        'icon': 'github',
        'category': 'dev',
        'kind': 'mcp_stdio',
        'command': 'npx',
        'args': ['-y', '@anthropic/mcp-github'],
        'requires_auth': True,
        'env_keys': ['GITHUB_TOKEN'],
        'tags': ['code_execution'],
    },
    {
        'id': 'google-maps',
        'name': 'Google Maps',
        'description': 'Geocoding, directions, places, and distance matrix via the Google Maps API.',
        'icon': 'google-maps',
        'category': 'search',
        'kind': 'mcp_stdio',
        'command': 'npx',
        'args': ['-y', '@modelcontextprotocol/server-google-maps'],
        'requires_auth': True,
        'env_keys': ['GOOGLE_MAPS_API_KEY'],
        'tags': ['search', 'maps', 'gcp'],
    },
    {
        'id': 'notion',
        'name': 'Notion',
        'description': 'Read and write Notion pages and databases via Notion\'s hosted MCP server.',
        'icon': 'notion',
        'category': 'productivity',
        'kind': 'mcp_oauth',
        'url': 'https://mcp.notion.com/mcp',
        'requires_auth': True,
        'tags': ['knowledge', 'communication'],
    },
    {
        'id': 'playwright',
        'name': 'Playwright',
        'description': 'Browser automation — navigate, click, screenshot.',
        'icon': 'playwright',
        'category': 'dev',
        'kind': 'mcp_stdio',
        'command': 'npx',
        'args': ['-y', '@anthropic/mcp-playwright'],
        'tags': ['web'],
    },
    {
        'id': 'slack',
        'name': 'Slack',
        'description': 'Send messages, read channels in Slack.',
        'icon': 'slack',
        'category': 'communication',
        'kind': 'mcp_stdio',
        'command': 'npx',
        'args': ['-y', '@anthropic/mcp-slack'],
        'requires_auth': True,
        'env_keys': ['SLACK_TOKEN'],
        'tags': ['communication'],
    },
]

print('Seeding MCP catalog...')
for m in mcp_catalog:
    doc_ref = db.collection('mcp_catalog').document()
    doc_ref.set(m)
    print(f'  ✓ {m[\"name\"]}')

print()
print(f'✅ Seeded {len(personas)} personas and {len(mcp_catalog)} MCP servers.')
"

echo "=== Seeding complete ==="
