#!/usr/bin/env bash
# Seed Firestore with initial data (default personas, MCP servers).
#
# Usage: ./seed-data.sh [project-id]
#
# Requires: gcloud CLI with Firestore access.
# Seeds data via a small Python script using firebase-admin.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"

echo "=== Seeding Firestore for project: ${PROJECT_ID} ==="

# Run the seed script using the backend's Python environment
cd "${SCRIPT_DIR}/../../backend"

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
mcp_catalog = [
    {
        'name': 'Google Search',
        'description': 'Search the web using Google Search API for real-time information.',
        'icon': '🔍',
        'category': 'search',
        'transport': 'builtin',
        'endpoint': '',
        'tools': ['google_search'],
    },
    {
        'name': 'GitHub',
        'description': 'Interact with GitHub repositories — browse code, issues, PRs, and more.',
        'icon': '🐙',
        'category': 'development',
        'transport': 'streamable_http',
        'endpoint': 'https://mcp.github.com/sse',
        'tools': ['search_repos', 'get_file_contents', 'list_issues', 'create_issue'],
    },
    {
        'name': 'Brave Search',
        'description': 'Privacy-focused web search with Brave Search API.',
        'icon': '🦁',
        'category': 'search',
        'transport': 'streamable_http',
        'endpoint': '',
        'tools': ['brave_search'],
    },
    {
        'name': 'Filesystem',
        'description': 'Read and write files on the connected desktop client.',
        'icon': '📁',
        'category': 'utilities',
        'transport': 'stdio',
        'endpoint': '',
        'tools': ['read_file', 'write_file', 'list_directory'],
    },
    {
        'name': 'Memory',
        'description': 'Persistent memory store for saving and recalling facts across sessions.',
        'icon': '🧠',
        'category': 'utilities',
        'transport': 'builtin',
        'endpoint': '',
        'tools': ['save_memory', 'recall_memory', 'search_memories'],
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
