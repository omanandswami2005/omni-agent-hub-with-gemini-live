# Omni Hub — Architecture Overview

> **One AI brain. Every device. Infinite capabilities.**

Omni is a multi-client, single-server AI agent hub for the Gemini Live Agent Challenge. Users speak to one intelligent agent from any device — web, mobile, CLI, smart glasses, desktop — and the agent acts across all of them simultaneously.

---

## Core Idea

```
                ┌─────────────────────────────────────────┐
                │         OMNI HUB BACKEND                │
                │          (Cloud Run)                    │
                │                                         │
                │   ┌───────────────────────────┐         │
                │   │      ADK Root Agent       │         │
                │   │   (Persona Dispatcher)    │         │
                │   │                           │         │
                │   │  Nova  Atlas  Sage  Spark │         │
                │   └─────────────┬─────────────┘         │
                │                 │                        │
                │   ┌─────────────┼─────────────┐         │
                │   │             │             │         │
                │   ▼             ▼             ▼         │
                │  T1 Core     T2 Plugin    T3 Client    │
                │  Tools       Registry     Proxy Tools  │
                │  (always)    (MCP/native) (reverse-RPC)│
                │                                         │
                │   ┌──────────────────────────┐          │
                │   │   ConnectionManager      │          │
                │   │   (per-user, per-device)  │          │
                │   └──────────┬───────────────┘          │
                └──────────────┼──────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │      Raw WebSocket (Binary      │
              │      audio + JSON control)      │
     ┌────────┴──┐  ┌──────┴──┐  ┌──────┴──┐  ┌──┴───────┐
     │ Web       │  │ Mobile  │  │ Desktop │  │ ESP32    │
     │ Dashboard │  │ (voice) │  │ (tray)  │  │ Glasses  │
     └───────────┘  └─────────┘  └─────────┘  └──────────┘
               ┌─────┴────┐  ┌──────┴──┐
               │   CLI    │  │ Chrome  │
               │ Terminal │  │ Ext.    │
               └──────────┘  └─────────┘
```

---

## Three Tool Tiers

The agent sees ONE flat list of tools. Behind the scenes, tools come from three independent tiers:

| Tier | Where | Who Manages | How to Add |
|------|-------|-------------|------------|
| **T1 — Core Backend** | `app/tools/` | Core team | Add Python function + wire into `agent_factory.py` |
| **T2 — Plugins** | `app/plugins/` or external MCP servers | Any developer | Drop a file in `app/plugins/` or write an MCP server |
| **T3 — Client-Local** | On device | Client developer | Advertise `local_tools` at connect, handle `tool_invocation` messages |

**T2 plugins** support four kinds:

| Kind | How | Example |
|------|-----|---------|
| `mcp_stdio` | Subprocess speaking MCP protocol | GitHub, Brave Search, Notion |
| `mcp_http` | Remote HTTP MCP server | Wikipedia |
| `native` | Python module with `FunctionTool` instances | Notification sender |
| `e2b` | E2B cloud sandbox for code execution | execute_code, install_package |

---

## Key Benefits for Developers

### 1. Independent Development Tracks
Five developer tracks that never touch each other's code:

| Track | What You Build | Files You Touch |
|-------|---------------|----------------|
| Plugin Developer | Python tools the agent can call | Only `app/plugins/your_plugin.py` |
| MCP Server Developer | External tool servers (any language) | Only your MCP server + one manifest entry |
| Client Developer | New device clients | Zero backend files — just implement the WS protocol |
| Frontend Developer | Dashboard UI | Only `dashboard/` directory |
| DevOps | Deployment & infra | Only `deploy/` directory |

### 2. Zero Backend Changes for New Clients
A new client (smart TV, car, IoT) connects via WebSocket, sends an auth message with its `client_type` and `capabilities`, and the agent automatically adapts. No backend code change required.

### 3. Plugin Store Pattern
Users enable/disable plugins via the dashboard. The agent immediately gains or loses capabilities. Developers add plugins by dropping a file — auto-discovered at startup.

### 4. Capability-Driven, Not Client-Specific
The backend never hardcodes "if desktop then..." logic. Tools are gated by what the client **advertises** it can do, not by its label.

---

## Key Services

| Service | File | Purpose |
|---------|------|---------|
| **PluginRegistry** | `app/services/plugin_registry.py` | T2 plugin lifecycle — connect, disconnect, toggle, evict idle |
| **ToolRegistry** | `app/services/tool_registry.py` | Assembles T1+T2+T3 into one tool list per session |
| **ConnectionManager** | `app/services/connection_manager.py` | Per-user WS registry, capability storage, heartbeat |
| **EventBus** | `app/services/event_bus.py` | Fan-out events to dashboard subscribers |
| **MCPManager** | `app/services/mcp_manager.py` | Backward-compat wrapper (delegates to PluginRegistry) |

---

## API Surface

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/init` | Bootstrap — sessions, personas, plugin catalog in one call |
| `GET /api/v1/plugins/catalog` | Full plugin list with per-user state |
| `POST /api/v1/plugins/toggle` | Enable/disable a plugin |
| `POST /api/v1/plugins/secrets` | Store API keys for a plugin |
| `GET /api/v1/plugins/{id}/tools` | Full tool schemas (on-demand) |
| `WS /ws/live` | Bidirectional audio + JSON (voice sessions) |
| `WS /ws/chat` | Text-only JSON (chat sessions) |
| `GET /docs` | Auto-generated OpenAPI docs |

---

## Test Coverage

**54 tests passing** across plugin registry, tool registry, capabilities, T3 proxy tools, and bug-fix verification. Run with:

```bash
cd backend
source .venv/Scripts/activate   # Windows
python -m pytest tests/test_services/ -v
```

---

## What's Next?

Read the guide for your specific track:

| Track | Guide |
|-------|-------|
| **Plugin Developer** (Python) | [01_PLUGIN_DEVELOPER.md](01_PLUGIN_DEVELOPER.md) |
| **MCP Server Developer** (any language) | [02_MCP_SERVER_DEVELOPER.md](02_MCP_SERVER_DEVELOPER.md) |
| **Client Developer** (any language) | [03_CLIENT_DEVELOPER.md](03_CLIENT_DEVELOPER.md) |
| **Frontend Developer** (React) | [04_FRONTEND_DEVELOPER.md](04_FRONTEND_DEVELOPER.md) |
| **DevOps & Deploy** | [05_DEVOPS_DEPLOY.md](05_DEVOPS_DEPLOY.md) |
