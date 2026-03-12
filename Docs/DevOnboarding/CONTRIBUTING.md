# Omni Hub — Contributing & Developer Onboarding

> **Hackathon**: Gemini Live Agent Challenge
> **Deadline**: March 17, 2026
> **Backend Status**: Production-ready (54 tests passing)

Welcome! This guide helps you pick a track and start contributing immediately.

---

## Pick Your Track

| # | Track | Guide | Difficulty | Language |
|---|-------|-------|------------|----------|
| 0 | **Architecture Overview** | [00_ARCHITECTURE_OVERVIEW.md](00_ARCHITECTURE_OVERVIEW.md) | — | Read first |
| 1 | **Plugin Developer** | [01_PLUGIN_DEVELOPER.md](01_PLUGIN_DEVELOPER.md) | Easy | Python |
| 2 | **MCP Server Developer** | [02_MCP_SERVER_DEVELOPER.md](02_MCP_SERVER_DEVELOPER.md) | Easy | Python (any lang ok) |
| 3 | **Client Developer** | [03_CLIENT_DEVELOPER.md](03_CLIENT_DEVELOPER.md) | Medium | Any language |
| 4 | **Frontend Developer** | [04_FRONTEND_DEVELOPER.md](04_FRONTEND_DEVELOPER.md) | Medium | React / JS |
| 5 | **DevOps & Deployment** | [05_DEVOPS_DEPLOY.md](05_DEVOPS_DEPLOY.md) | Medium | Bash / Docker / Terraform |
| 6 | **Tools & Plugins Comparison** | [06_TOOLS_AND_PLUGINS_COMPARISON.md](06_TOOLS_AND_PLUGINS_COMPARISON.md) | — | Read for choosing approach |

---

## How It All Fits Together

```
                    ┌─────────────────────────────┐
                    │     Omni Hub Backend          │
                    │     (FastAPI + ADK)           │
                    │                               │
  Track 1 & 2 ──►  │  ToolRegistry  PluginRegistry │
                    │     T1  T2  T3                │
                    │                               │
  Track 3 ──────►  │  ConnectionManager  EventBus   │  ◄── Track 5
                    │     WS /ws/chat  /ws/live      │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
               Track 4          Track 3          Track 3
               Web Dashboard    CLI Client       Other Clients
               (React 19)      (Python)         (Any language)
```

- **Track 1** (Plugin) & **Track 2** (MCP): Add new tools the agent can use
- **Track 3** (Client): Build new surfaces that connect via WebSocket
- **Track 4** (Frontend): Improve the React web dashboard
- **Track 5** (DevOps): Deploy and operate the system

All tracks are **independent** — you can work on any track without touching others.

---

## Getting Started (All Tracks)

### 1. Clone the repo

```bash
git clone <repo-url>
cd Gemini-live-agent-hackathon
```

### 2. Set up the backend (needed by all tracks)

```bash
cd backend
uv sync
cp .env.example .env
# Edit .env with your credentials (see 05_DEVOPS_DEPLOY.md)
uv run uvicorn app.main:app --reload --port 8000
```

### 3. Verify everything works

```bash
cd backend
python -m pytest tests/ -v
# Expected: 54 tests passing
```

### 4. Read the architecture overview

Start with [00_ARCHITECTURE_OVERVIEW.md](00_ARCHITECTURE_OVERVIEW.md), then dive into your track guide.

---

## Key Concepts

| Concept | What It Means |
|---------|--------------|
| **T1 Tools** | Built-in Python functions (fastest, always available) |
| **T2 Tools** | MCP server tools (loaded via plugins) |
| **T3 Tools** | Client-side tools (run on user's device, reverse-RPC) |
| **Plugin** | A package that contributes tools (native Python or MCP server) |
| **Client** | Any frontend/device that connects via WebSocket |
| **Persona** | An agent personality (teacher, developer, analyst, etc.) |
| **GenUI** | Agent-generated UI components (dynamic cards, forms, charts) |
| **Cross-client** | Actions that span multiple devices (glasses → desktop) |

---

## API Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `ws://host:8000/ws/chat` | WS | Text-only agent chat |
| `ws://host:8000/ws/live` | WS | Bidirectional audio + text |
| `/api/v1/auth/verify` | POST | Verify Firebase token |
| `/api/v1/init/bootstrap` | POST | Init session + get config |
| `/api/v1/plugins/catalog` | GET | List all plugins |
| `/api/v1/plugins/toggle` | POST | Enable/disable a plugin |
| `/api/v1/personas/list` | GET | List personas |
| `/api/v1/clients/online` | GET | Online clients |
| `/health` | GET | Health check |

---

## Branching Convention

```
main                          # Stable, tested code
├── feat/plugin-weather       # Track 1: new plugin
├── feat/mcp-notion-server    # Track 2: new MCP server
├── feat/vscode-client        # Track 3: new client
├── feat/dashboard-genui      # Track 4: frontend feature
└── feat/ci-pipeline          # Track 5: DevOps
```

- Create feature branches from `main`
- Keep PRs focused on one track
- Include tests for new functionality

---

## File Ownership

| Track | You own | Don't touch |
|-------|---------|-------------|
| 1 (Plugin) | `backend/app/plugins/your_plugin.py` | Core services |
| 2 (MCP) | `backend/scripts/your_server.py` + plugin file | Core services |
| 3 (Client) | `cli/`, `desktop-client/`, `chrome-extension/`, `smart-glasses/` | Backend WS endpoints |
| 4 (Frontend) | `dashboard/src/` | Backend code |
| 5 (DevOps) | `deploy/`, Dockerfiles, CI configs | Application logic |

---

## Need Help?

- Read the architecture overview: [00_ARCHITECTURE_OVERVIEW.md](00_ARCHITECTURE_OVERVIEW.md)
- Check existing examples in the codebase (TEMPLATE.py, omni_cli.py, local_mcp_server.py)
- Look at tests for expected behavior: `backend/tests/`
- Ask questions in the team channel
