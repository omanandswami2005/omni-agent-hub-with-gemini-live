<div align="center">

# OMNI

### Speak anywhere. Act everywhere.

One AI brain. Every device. Infinite capabilities.

[![Gemini Live Agent Challenge](https://img.shields.io/badge/Hackathon-Gemini%20Live%20Agent%20Challenge-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://googleai.devpost.com/)
[![Category](https://img.shields.io/badge/Category-Live%20Agents-FF6F00?style=for-the-badge)](https://googleai.devpost.com/)
[![Built with](https://img.shields.io/badge/Built%20with-Google%20ADK-34A853?style=for-the-badge&logo=google&logoColor=white)](https://google.github.io/adk-docs/)
[![Powered by](https://img.shields.io/badge/Powered%20by-Gemini%20Live%20API-8E24AA?style=for-the-badge&logo=google&logoColor=white)](https://cloud.google.com/vertex-ai/generative-ai/docs/live-api)

---

**Omni** is a multi-client AI agent hub that lets you speak to one intelligent agent from any device — web dashboard, mobile, Chrome extension, desktop, or smart glasses — and have it act across all of them simultaneously.

[Demo Video](#demo) · [Architecture](#architecture) · [Getting Started](#getting-started) · [Blog Post](#blog-post)

</div>

---

## The Problem

AI assistants today live in text boxes on single screens. You can't speak to your AI while wearing safety glasses on a factory floor. You can't add new capabilities without waiting for the next software update. You can't switch devices mid-thought and pick up where you left off.

**Every AI assistant is an island.**

## The Solution

**Omni** connects one AI brain to every device you own. Speak from your phone, see results on your dashboard, trigger actions on your desktop — all in one continuous conversation.

- **One voice, every device** — Web, mobile, Chrome extension, desktop tray app, ESP32 glasses
- **MCP Plugin Store** — Install new agent capabilities in one click, like an app store for AI skills
- **GenUI** — Agent renders live charts, tables, code blocks, and cards on your dashboard while speaking to you
- **Agent Personas** — Switch between specialized AI personalities (analyst, coder, researcher) with distinct voices and skills
- **Browser Control** — Tell your agent to scrape a website, fill a form, or extract data — all by voice
- **Cross-Client Actions** — Say "save this to my dashboard" from your phone → it appears on your desktop instantly

---

## Demo

> 🎥 [Watch the 4-minute demo video →](#) *(coming soon)*

### Highlights

| Moment | What Happens |
|---|---|
| **Voice + GenUI** | Ask about stock performance → agent speaks the answer while a chart renders live on the dashboard |
| **Persona Switch** | "Switch to Atlas" → voice changes instantly → ask for code → code block renders → "Execute it" → runs in sandbox |
| **MCP Plugin Toggle** | Enable Brave Search with one click → agent immediately searches the web → disable it → agent falls back gracefully |
| **Cross-Client** | Point phone camera at an object → agent describes it → "Saved to your dashboard" → switch to desktop → it's there |

---

## Architecture

### 3-Layer Capability-Based Agent Routing

```
                    ┌────────────────────────────────────────────┐
                    │              OMNI HUB (Cloud Run)          │
                    │                                            │
                    │  ┌──────────────────────────────────────┐  │
                    │  │        Root Agent "omni_root"        │  │
                    │  │         tools: [plan_task]            │  │
                    │  ├──────────────────────────────────────┤  │
                    │  │                                      │  │
                    │  │  LAYER 1 — Persona Pool              │  │
                    │  │  ┌──────────┐  ┌──────────┐         │  │
                    │  │  │assistant │  │  coder   │         │  │
                    │  │  │search,web│  │code,sandbox│       │  │
                    │  │  └──────────┘  └──────────┘         │  │
                    │  │  ┌──────────┐  ┌──────────┐         │  │
                    │  │  │researcher│  │ analyst  │         │  │
                    │  │  │search,kb │  │data,code │         │  │
                    │  │  └──────────┘  └──────────┘         │  │
                    │  │  ┌──────────┐                       │  │
                    │  │  │ creative │                       │  │
                    │  │  │media,art │                       │  │
                    │  │  └──────────┘                       │  │
                    │  │                                      │  │
                    │  │  LAYER 2 — TaskArchitect             │  │
                    │  │  (plan_task FunctionTool)            │  │
                    │  │  Decomposes complex multi-step tasks │  │
                    │  │                                      │  │
                    │  │  LAYER 3 — device_agent              │  │
                    │  │  Cross-client orchestration (T3)     │  │
                    │  │                                      │  │
                    │  ├──────────────────────────────────────┤  │
                    │  │  MCP Plugin System (Dynamic T2 Tools)│  │
                    │  │  Capability-tagged per persona       │  │
                    │  └──────────────────────────────────────┘  │
                    └────────────────┬───────────────────────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 │     Raw WebSocket (Binary audio     │
                 │        + JSON control)              │
                 │                  │                   │
        ┌────────┴───┐  ┌──────────┴──┐  ┌────────────┴──┐
        │ Web        │  │ Mobile      │  │ Chrome        │
        │ Dashboard  │  │ PWA         │  │ Extension     │
        │ (React)    │  │ (Camera)    │  │ (Voice)       │
        └────────────┘  └─────────────┘  └───────────────┘
        ┌─────────────┐  ┌─────────────┐
        │ Desktop     │  │ ESP32       │
        │ Tray App    │  │ Glasses     │
        │ (Python)    │  │ (Protocol)  │
        └─────────────┘  └─────────────┘
```

### Key Design Decisions

| Decision | Choice | Why |
|---|---|---|
| Audio Transport | Binary WebSocket frames | 33% smaller than base64-in-JSON, lower latency |
| Audio Pipeline | AudioWorklet (not ScriptProcessor) | Runs on separate thread, zero main-thread jank |
| Agent Framework | Google ADK with `run_live()` | Native bidi streaming, multi-agent orchestration |
| Plugin System | MCP (Model Context Protocol) | Open standard, 10,000+ community tools |
| GenUI | Agent returns structured JSON → React renders | Audio + visual output simultaneously |
| Session Persistence | Vertex AI Agent Engine Sessions | Survives Cloud Run restarts, Google-managed |

---

## Tech Stack

### Backend
| Component | Technology |
|---|---|
| Runtime | Python 3.12+ |
| Package Manager | uv |
| API Server | FastAPI + Uvicorn |
| Agent Framework | Google ADK v0.5+ |
| Audio Model | `gemini-live-2.5-flash-native-audio` |
| Code Execution | E2B Sandbox + Agent Engine Code Execution |

### Frontend
| Component | Technology |
|---|---|
| Framework | React 19 (JavaScript) |
| Build Tool | Vite |
| Styling | Tailwind CSS 4 + shadcn/ui |
| State | Zustand |
| Charts | Recharts |
| Icons | Lucide React |
| Toasts | Sonner |

### Google Cloud Services (16+)
| Category | Services |
|---|---|
| **Vertex AI** | Gemini Live API, ADK, Grounding (Google Search + Maps), Agent Engine (Sessions + Memory Bank + Code Execution), Gen AI Evaluation, Imagen 4 |
| **Infrastructure** | Cloud Run, Firestore, Firebase Auth, Cloud Storage, Secret Manager, Artifact Registry |
| **Observability** | Cloud Logging, Cloud Monitoring, Cloud Trace |
| **DevOps** | Cloud Build, Terraform |

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Google Cloud account with billing enabled
- Google Cloud CLI (`gcloud`)

### 1. Clone the repository

```bash
git clone https://github.com/omanandswami2005/omni-agent-hub-with-gemini-live.git
cd omni-agent-hub-with-gemini-live
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env with your API keys:
#   GOOGLE_CLOUD_PROJECT=your-project-id
#   GOOGLE_CLOUD_LOCATION=us-central1
#   E2B_API_KEY=your-e2b-key
```

### 3. Start the backend

```bash
cd backend
uv sync
uv run uvicorn main:app --reload --port 8000
```

### 4. Start the frontend

```bash
cd frontend
pnpm install
pnpm run dev
```

### 5. Open the dashboard

Navigate to `http://localhost:5173` — click "Sign in with Google" and start talking.

---

## Deploy to Google Cloud

### One-command deploy

```bash
cd deploy
terraform init
terraform apply
```

### Manual deploy

```bash
# Build and push container
gcloud builds submit --tag gcr.io/$PROJECT_ID/omni-backend

# Deploy to Cloud Run
gcloud run deploy omni-backend \
  --image gcr.io/$PROJECT_ID/omni-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances 1 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID"
```

---

## Agent Personas

Omni ships with 5 specialized AI personas. Each persona declares **capabilities** and receives only the tools that match via the `ToolCapability` tag system:

| Persona | Role | Voice | Capabilities | Tools Received |
|---|---|---|---|---|
| **assistant** | General Assistant | Puck | search, web, knowledge, communication, media | google_search, rag_query, notification_sender + matched MCP |
| **coder** | Code & Debug | Kore | code_execution, sandbox, search, web | google_search, code_execution, e2b_sandbox + matched MCP |
| **researcher** | Deep Research | Aoede | search, web, knowledge | google_search + matched MCP |
| **analyst** | Data & Finance | Charon | code_execution, sandbox, search, data, web | google_search, code_execution, e2b_sandbox + matched MCP |
| **creative** | Content Creation | Fenrir | creative, media | imagen, creative_tools + matched MCP |

Switch personas by voice: *"Switch to coder"* — or click the persona panel on the dashboard.

Create custom personas with capability tags: *"Create a new persona called Chef with knowledge and search capabilities."*

---

## MCP Plugin Store

Omni's agent capabilities are extensible at runtime through the **PluginRegistry** — a unified plugin system supporting MCP servers (local, remote, and OAuth-secured), native Python modules, and E2B sandboxes. Enable/disable any plugin with a single toggle — the agent adapts instantly. No restart required.

### Extension Points

| Method | What | How |
|---|---|---|
| **Native plugin** | Python function tools | Drop `.py` in `backend/app/plugins/` with a `MANIFEST` → auto-discovered |
| **MCP server** | Stdio, HTTP, or OAuth MCP servers | Drop `.json` in `backend/app/mcps/` → auto-discovered at startup |
| **OAuth MCP** | Remote servers with OAuth 2.0 | Set `kind: "mcp_oauth"` with `url` + `oauth` config → one-click connect in UI |
| **Runtime API** | Register via HTTP | `POST /api/v1/plugins/register` → persisted to `mcps/` JSON + live immediately |

### Built-in Catalog

| Plugin | What It Does | Kind |
|---|---|---|
| Brave Search | Web search via Brave API | MCP Stdio |
| GitHub | Repo management, issues, PRs | MCP Stdio |
| Slack | Send/read messages | MCP Stdio |
| Notion | Read/write Notion pages (official) | MCP OAuth |
| Playwright | Browser automation and scraping | MCP Stdio |
| Filesystem | Read/write sandboxed files | MCP Stdio |
| E2B Sandbox | Code execution (100+ languages) | E2B |
| Wikipedia | Encyclopedia lookups | Native Plugin |
| RAG Documents | Upload & search documents | Native Plugin |
| Notification Sender | Webhook/log notifications | Native Plugin |

### Add a New MCP Server (3 ways)

**1. JSON config file (recommended)**
```bash
# Copy the template
cp backend/app/mcps/TEMPLATE.json backend/app/mcps/my-server.json
# Edit id, name, command, args, tags — restart backend
```

**2. API registration (runtime, no restart)**
```bash
curl -X POST http://localhost:8000/api/v1/plugins/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "my-server",
    "name": "My MCP Server",
    "kind": "mcp_stdio",
    "command": "npx",
    "args": ["-y", "@my-org/mcp-server"],
    "tags": ["search", "web"]
  }'
# Immediately available in catalog — persisted to mcps/my-server.json
```

**3. Native Python plugin**
```bash
cp backend/app/plugins/TEMPLATE.py backend/app/plugins/my_plugin.py
# Edit MANIFEST, implement tool functions — restart backend
```

**Create your own plugin** in 5 minutes. See [TEMPLATE.py](backend/app/plugins/TEMPLATE.py) or [TEMPLATE.json](backend/app/mcps/TEMPLATE.json).

**54 tests** cover plugin lifecycle, tool discovery, T3 proxy tools, and hardening fixes.

---

## Project Structure

```
omni-agent-hub-with-gemini-live/
├── backend/                    # Python FastAPI + ADK
│   ├── app/
│   │   ├── agents/             # Agent definitions
│   │   │   ├── root_agent.py   # Root orchestrator (3-layer routing)
│   │   │   ├── agent_factory.py # Capability-based per-persona builder
│   │   │   ├── cross_client_agent.py # device_agent (Layer 3)
│   │   │   └── task_planner_tool.py  # TaskArchitect plan_task tool (Layer 2)
│   │   ├── api/                # REST + WebSocket endpoints
│   │   │   ├── ws_live.py      # /ws/live (audio) + /ws/chat (text)
│   │   │   ├── plugins.py      # Plugin catalog, toggle, schemas
│   │   │   └── init.py         # Bootstrap endpoint (single-trip load)
│   │   ├── tools/              # T1 core tools
│   │   │   └── cross_client.py # Cross-device action tools
│   │   ├── services/           # Business logic singletons
│   │   │   ├── plugin_registry.py   # T2 plugin lifecycle (MCP+native+E2B)
│   │   │   ├── tool_registry.py     # Per-persona T1+T2+T3 via capability matching
│   │   │   ├── connection_manager.py # WS registry + capability storage
│   │   │   ├── mcp_manager.py       # Backward-compat wrapper
│   │   │   └── event_bus.py         # Dashboard event fan-out
│   │   ├── plugins/            # Auto-discovered native plugins
│   │   │   ├── notification_sender.py # Example native plugin
│   │   │   └── TEMPLATE.py     # Developer template (copy to create plugins)
│   │   ├── mcps/               # MCP server configs (JSON auto-discovery)
│   │   │   ├── TEMPLATE.json   # Copy to add a new MCP server
│   │   │   ├── brave-search.json # Brave Search, GitHub, Slack, etc.
│   │   │   └── ...             # Drop JSON here → auto-discovered at startup
│   │   ├── models/             # Pydantic schemas
│   │   ├── middleware/         # Auth, CORS
│   │   └── utils/              # Logging, errors
│   ├── scripts/                # MCP test servers
│   ├── tests/                  # 54 pytest tests
│   │   └── test_services/      # Plugin registry, tool registry, bug fixes
│   └── cli/                    # CLI client
│       └── omni_cli.py         # Text-only agent in terminal
├── dashboard/                  # React 19 + Vite
│   ├── src/
│   │   ├── components/         # UI components (shadcn/ui)
│   │   ├── pages/              # Dashboard, Personas, Plugins, Sessions...
│   │   ├── stores/             # Zustand state stores
│   │   ├── hooks/              # useWebSocket, useAudioPipeline, etc.
│   │   └── lib/                # Utilities
│   └── index.html
├── Docs/                       # Architecture & planning
│   ├── UNIFIED_MULTI_CLIENT_ARCHITECTURE.md  # Master architecture doc
│   ├── DEVELOPMENT_CHECKLIST.md
│   └── ...
├── deploy/
│   ├── terraform/              # Cloud Run + Firestore + GCS + Secret Manager
│   └── scripts/
├── .env.example
└── README.md
```

---

## How It Works

### Voice Pipeline

```
User speaks → Mic → AudioWorklet (16kHz PCM)
  → Binary WebSocket frame → FastAPI backend
    → ADK LiveRequestQueue → Gemini Live API
      → Agent processes (tools, grounding, GenUI)
    ← ADK response (audio + text + structured data)
  ← Binary frame (24kHz PCM) + JSON frames (transcript, GenUI, status)
← AudioWorklet playback → Speaker

Latency target: < 500ms end-to-end
```

### Cross-Client Actions

```
Phone camera → captures image → sends via WebSocket
  → Agent: "This is a book about machine learning"
  → Agent: "I've saved the analysis to your dashboard"
  → WebSocket push to dashboard client
    → GenUI card appears with image + analysis

All clients share the same session via Agent Engine Sessions
```

### GenUI Flow

```
User: "Show me Tesla's stock performance"

Agent response:
  Audio: "Tesla has been on an upward trend..."
  GenUI: {
    type: "chart",
    chartType: "line",
    data: [...],
    title: "Tesla (TSLA) — 12 Month Performance"
  }

Dashboard renders Recharts component inline in chat
while audio plays simultaneously
```

---

## Judging Criteria Alignment

| Criterion | Weight | Our Score Target | Key Features |
|---|---|---|---|
| **Innovation & Multimodal UX** | 40% | 5/5 | Multi-client hub, GenUI, cross-client actions, voice personas, MCP plugin store, browser control |
| **Technical Implementation** | 30% | 5/5 | 14 ADK features, 16+ GCP services, Agent Engine, binary audio transport, AudioWorklet pipeline |
| **Demo & Presentation** | 30% | 5/5 | 4-min scripted video with "wow" moments, architecture diagram, Cloud deployment proof |
| **Bonus** | +1.0 | +1.0 | Blog post (+0.6), Terraform deploy (+0.2), GDG membership (+0.2) |

---

## Blog Post

> 📝 [How I Built a Multi-Device AI Agent Hub with Gemini Live API & Google ADK →](#) *(coming soon)*

---

## Team

| Name | Role |
|---|---|
| **Your Name** | Full-stack developer |

---

## License

This project is built for the [Gemini Live Agent Challenge](https://googleai.devpost.com/) hackathon.

---

<div align="center">

**OMNI** — Speak anywhere. Act everywhere.

Built with ❤️ using Google Gemini, ADK, and 16+ Google Cloud services.

</div>
