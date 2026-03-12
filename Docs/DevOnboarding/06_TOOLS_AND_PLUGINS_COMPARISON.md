# Tool & Plugin Architecture — Comparison Guide

> When to use what, real-world trade-offs, and what's available to test today.

---

## The Four Ways to Give the Agent Capabilities

Omni Hub has **four distinct mechanisms** to extend the agent. Each has different trade-offs in performance, isolation, language flexibility, and deployment complexity.

| Mechanism | Tier | Where It Runs | Language | Latency | Isolation |
|-----------|------|--------------|----------|---------|-----------|
| **T1 Built-in Tool** | T1 | Backend process (in-memory) | Python only | ~1ms | None (shares process) |
| **Native Plugin** | T2 | Backend process (in-memory) | Python only | ~1ms | Module-level |
| **MCP Server (stdio)** | T2 | Child subprocess | Any language | ~50-200ms | Full process |
| **MCP Server (http)** | T2 | Remote service | Any language | ~100-500ms | Full network |
| **Client-Local Tool (T3)** | T3 | User's device | Any language | ~200-2000ms | Full device |

---

## Detailed Comparison

### T1 Built-in Tools — `backend/app/tools/*.py`

**What it is**: Python async functions registered directly into the agent at startup. Hardwired to specific personas in `agent_factory.py`.

**Advantages**:
- Fastest possible execution (in-process, no IPC overhead)
- Full access to all backend services (ConnectionManager, Firestore, GCS, EventBus)
- No serialisation/deserialisation overhead
- Always available — cannot be disabled by users
- Easiest to debug (standard Python debugging)

**Disadvantages**:
- Python only — no other languages
- No isolation — a crash can take down the entire backend
- Cannot be toggled on/off per user (hardwired to personas)
- Requires backend restart to update
- Tight coupling to backend internals

**Best for**: Core platform capabilities that every user needs — image generation, code execution, search, cross-client messaging.

---

### Native Plugin — `backend/app/plugins/your_plugin.py`

**What it is**: A Python module with a `MANIFEST` dict and a `get_tools()` factory function. Auto-discovered at startup, user-toggleable via the dashboard.

**Advantages**:
- Same speed as T1 (in-process execution)
- User can enable/disable through the dashboard
- Auto-discovered — just drop a file in `app/plugins/`
- Supports `requires_auth` for API key gating
- Full access to backend services
- Appears in the plugin catalog/marketplace UI

**Disadvantages**:
- Python only
- No process isolation (crash affects backend)
- Requires backend restart for new plugins (hot-reload works in dev)
- Must follow the MANIFEST + factory convention

**Best for**: Team-built tools that users should be able to opt-in to — notification systems, custom integrations, internal APIs.

---

### MCP Server (stdio) — subprocess

**What it is**: A standalone program that speaks the MCP protocol over stdin/stdout. The backend spawns it as a child process when the user enables the plugin.

**Advantages**:
- **Any programming language** (Python, Node.js, Go, Rust, etc.)
- Full process isolation — crash doesn't affect backend
- Huge ecosystem — 100s of community MCP servers available
- Can use system resources (file system, network, databases)
- Lazy loading — only spawned when needed
- Clean separation of concerns

**Disadvantages**:
- Higher latency (~50-200ms per tool call due to IPC)
- Subprocess management overhead (spawn, monitor, cleanup)
- Cannot directly access backend services (must go through MCP protocol)
- Debugging requires attaching to the subprocess
- Resource consumption — each enabled MCP server is a running process
- Platform-dependent paths/executables

**Best for**: Integrating external services (GitHub, Notion, Slack), filesystem access, browser automation, any tool that benefits from isolation or is written in another language.

---

### MCP Server (http) — remote service

**What it is**: An MCP server running as a remote HTTP/SSE service. The backend connects to it over the network.

**Advantages**:
- **Any language, any machine** — can run on a different server entirely
- Best isolation — completely independent deployment
- Can scale independently of the backend
- Shared across multiple backend instances
- Can be managed by a different team/service

**Disadvantages**:
- Highest latency (~100-500ms per call, network dependent)
- Network dependency — can fail due to connectivity issues
- Requires separate deployment and monitoring
- Authentication/authorization complexity
- Cannot access local filesystem or resources

**Best for**: Shared enterprise services, third-party SaaS integrations, tools that need independent scaling, microservice architectures.

---

### T3 Client-Local Tools — runs on user's device

**What it is**: Tools advertised by a connected client (desktop app, Chrome extension, etc.) at WebSocket handshake time. The agent calls them via reverse-RPC — the backend proxies the call to the client device.

**Advantages**:
- **Runs on the user's actual device** — can access their files, apps, screen
- Any language (client-side implementation)
- No backend deployment needed for new tools
- Context-aware — tools know about the user's local environment
- Enables cross-device workflows (glasses → desktop)

**Disadvantages**:
- Highest and most variable latency (~200-2000ms, depends on device/network)
- 30-second timeout — tool must complete fast
- Client must be online and connected
- No guarantee of availability (user can disconnect anytime)
- Harder to test (requires running client + backend)
- Security-sensitive — executing on user's machine

**Best for**: Desktop automation, file management, screen capture, local app control, IoT device control, any action that must happen on the user's physical device.

---

## Decision Matrix — When to Choose What

| Scenario | Recommended | Why |
|----------|-------------|-----|
| Core feature everyone needs | **T1 Built-in** | Always available, fastest, no user action needed |
| Team-built tool users can opt-in | **Native Plugin** | Dashboard toggle, fast, Python ecosystem |
| External service integration (Notion, Slack) | **MCP stdio** | Community servers exist, process isolation |
| Tool in Node.js/Go/Rust | **MCP stdio** | Language-agnostic |
| Enterprise service on another server | **MCP http** | Network isolation, independent scaling |
| Access user's local files/apps | **T3 Client-Local** | Must run on user's device |
| Screen capture / desktop automation | **T3 Client-Local** | Needs physical device access |
| Quick prototype / hackathon tool | **Native Plugin** | Fastest to develop, drop-in file |
| Production microservice | **MCP http** | Best isolation, scaling, monitoring |
| Browser automation | **MCP stdio** (Playwright) | Existing MCP server, process isolation |

---

## Real-World Interaction Use Cases

### Use Case 1: "Search Wikipedia and summarize"
```
User (voice): "Find information about quantum computing on Wikipedia"
→ Agent calls: T2 MCP tool (wikipedia server) → search_wikipedia("quantum computing")
→ Result: Article summary returned to agent
→ Agent responds via voice with summary
```
**Mechanism**: MCP stdio (`wikipedia` plugin) — external data source, benefits from isolation.

### Use Case 2: "Generate an image of a sunset"
```
User (voice): "Create an image of a sunset over Tokyo"  
→ Agent calls: T1 tool → generate_image(prompt="sunset over Tokyo")
→ Backend: Calls Imagen 4 API, uploads to GCS
→ Server pushes: image_response message over WebSocket
→ Dashboard: Renders image inline in chat
```
**Mechanism**: T1 built-in — needs direct access to GCS, WS connection, must be fast and reliable.

### Use Case 3: "Run this Python code"
```
User (voice): "Run a Python script that calculates fibonacci numbers up to 100"
→ Agent calls: T1 tool → execute_code(code="def fib(n):\n  ...")
→ Backend: Creates/reuses E2B sandbox, executes code
→ Result: stdout/stderr returned to agent
→ Agent reads output aloud
```
**Mechanism**: T1 built-in (E2B) — core capability, needs sandbox management, session persistence.

### Use Case 4: "Open VS Code on my desktop"
```
User (glasses, voice): "Open VS Code on my desktop and create a new file"
→ Agent calls: T1 cross-client → send_to_desktop(action="open_application", payload={"app": "code"})
→ Backend sends: cross_client message to desktop client over WS
→ Desktop app: Receives and launches VS Code
```
**Mechanism**: T1 cross-client tool → T3 execution on desktop device. The agent uses a T1 tool to route the command, the actual execution happens T3 client-side.

### Use Case 5: "Show me a weather dashboard"
```
User (voice): "Show a weather comparison dashboard for Tokyo and London"
→ Agent calls: T1 tool → send_to_dashboard(action="render_genui", payload={
    "type": "chart", "data": [...], "chart_type": "bar"
  })
→ Dashboard: Renders a dynamic GenUI chart component
```
**Mechanism**: T1 cross-client + GenUI — agent generates UI spec, dashboard renders it. GenUI is NOT a tool — it's a payload type within `send_to_dashboard`.

### Use Case 6: "Create a Notion page with my meeting notes"
```
User (voice): "Create a Notion page titled 'Meeting Notes March 12'"
→ User enables Notion plugin in dashboard (provides NOTION_TOKEN)
→ Agent calls: T2 MCP tool → notion_create_page(title="Meeting Notes March 12")
→ MCP server: Calls Notion API, creates page
→ Agent confirms: "Created the page in your Notion workspace"
```
**Mechanism**: MCP stdio (`notion` plugin) — external API, requires user auth token, benefits from process isolation.

### Use Case 7: "Read the file on my desktop"
```
User (CLI): "What's in my notes.txt file?"
→ CLI client advertised: local_tools = [{name: "read_file", ...}]
→ Agent calls: T3 proxy → read_file(path="/home/user/notes.txt")  
→ Backend sends: tool_invocation to CLI over WS
→ CLI client: Reads file, sends tool_result back
→ Agent: Reads content and summarizes
```
**Mechanism**: T3 client-local — file lives on user's device, only their client can access it.

---

## What's Available to Test RIGHT NOW (Voice + Dashboard)

### T1 Built-in Tools — Always On

These work immediately with voice interaction through the dashboard or CLI:

| Tool | Personas | Voice Example |
|------|----------|---------------|
| `google_search` | assistant, researcher, analyst | "Search for the latest news about AI" |
| `generate_image` | assistant, researcher, analyst, coder, creative | "Generate an image of a cat wearing a hat" |
| `generate_rich_image` | same as above | "Create an illustrated guide for making pasta" |
| `execute_code` | coder, analyst | "Run a Python script that prints hello world" |
| `install_package` | coder, analyst | "Install the requests library in the sandbox" |
| `send_to_desktop` | all personas | "Send this to my desktop" |
| `send_to_chrome` | all personas | "Open this URL in my Chrome extension" |
| `send_to_dashboard` | all personas | "Show me a chart of this data" (GenUI) |
| `notify_client` | all personas | "Send me a notification" |
| `list_connected_clients` | all personas | "What devices do I have connected?" |
| `upload_document` | researcher, analyst | "Upload this document for search" |
| `search_documents` | researcher, analyst | "Search my uploaded documents for X" |

### T2 Plugins — Enable in Dashboard Plugin Store

Enable these from the MCP Store page, then use via voice:

| Plugin | Requires API Key? | Voice Example |
|--------|-------------------|---------------|
| `wikipedia` | No | "Look up quantum computing on Wikipedia" |
| `filesystem` | No | "List files in the current directory" |
| `e2b-sandbox` | No (uses backend E2B key) | "Execute this code in a sandbox" |
| `brave-search` | Yes (`BRAVE_API_KEY`) | "Search Brave for Python tutorials" |
| `github` | Yes (`GITHUB_TOKEN`) | "List my GitHub repositories" |
| `playwright` | No | "Take a screenshot of google.com" |
| `notion` | Yes (`NOTION_TOKEN`) | "Create a Notion page" |
| `slack` | Yes (`SLACK_TOKEN`) | "Send a Slack message to #general" |
| `notification-sender` | No | "Send a notification to my connected clients" |

### T3 Client-Local — Depends on Connected Clients

These appear dynamically when clients connect and advertise capabilities:

| Client | Example T3 Tools | How to Test |
|--------|-----------------|-------------|
| CLI (`cli/omni_cli.py`) | Whatever you define in `--local-tools` | Run CLI with `--capabilities read_file` |
| Desktop (`desktop-client/`) | `capture_screen`, `open_application`, etc. | Run the desktop tray client |
| Chrome Extension (`chrome-extension/`) | `get_current_tab`, `open_url`, etc. | Load the Chrome extension |

---

## Category Classification

### Where does E2B fit?

| Aspect | Classification |
|--------|---------------|
| **Tier** | T1 (built-in) AND T2 (plugin) |
| **Plugin Category** | `SANDBOX` |
| **T1 Tools** | `execute_code`, `install_package` in `app/tools/code_exec.py` |
| **T2 Plugin** | `e2b-sandbox` plugin (kind: `e2b`) in `_builtin_plugins()` |
| **Backend Service** | `app/services/e2b_service.py` — manages `AsyncSandbox` lifecycle |
| **Fallback** | Agent Engine code execution (Vertex AI) if E2B unavailable |

E2B is available **two ways**: as always-on T1 tools for coder/analyst personas, AND as a toggleable T2 plugin for other personas. The T1 path is faster; the T2 path lets non-default personas use it.

### Where does GenUI fit?

| Aspect | Classification |
|--------|---------------|
| **Tier** | T1 (cross-client tool) |
| **Category** | Not a plugin — it's a **response payload type** |
| **Tool** | `send_to_dashboard(action="render_genui", payload={...})` |
| **Message Type** | `AgentResponse` with `content_type: "genui"` |
| **Frontend** | `dashboard/src/components/genui/` renders the dynamic UI |

GenUI is NOT a separate tool or plugin. It's a feature of the `send_to_dashboard` cross-client tool. The agent generates a JSON UI specification, sends it to the dashboard, and the React frontend renders it as interactive components (cards, charts, forms, tables).

### Where does Image Generation fit?

| Aspect | Classification |
|--------|---------------|
| **Tier** | T1 (built-in tools) |
| **Category** | `CREATIVE` (if it were a plugin — it's built-in) |
| **Tools** | `generate_image` (Imagen 4) + `generate_rich_image` (Gemini interleaved) |
| **Backend** | `app/tools/image_gen.py` — calls Vertex AI Imagen API |
| **Storage** | Uploads to GCS bucket, returns signed URL |
| **Message Type** | `ImageResponseMessage` pushed over WebSocket |
| **Personas** | assistant, researcher, analyst, coder, creative |

Image generation is a T1 built-in because it needs direct access to GCS upload, WebSocket push, and must be fast and reliable. It's not a plugin because every user should have access without toggling.

---

## Summary — Quick Decision Flowchart

```
Need to add a new capability?
│
├── Must run on user's device (file access, screen, apps)?
│   └── T3 Client-Local Tool
│
├── Is it a core feature every user needs?
│   └── T1 Built-in Tool
│
├── Should users be able to toggle it on/off?
│   │
│   ├── Written in Python?
│   │   └── Native Plugin (T2)
│   │
│   ├── Written in another language?
│   │   └── MCP Server stdio (T2)
│   │
│   └── Runs on a remote server?
│       └── MCP Server http (T2)
│
└── Quick prototype?
    └── Native Plugin (drop a .py file in app/plugins/)
```

---

## Performance Expectations

| Mechanism | Typical Latency | Startup Cost | Memory |
|-----------|----------------|--------------|--------|
| T1 Built-in | 1-5ms | None (loaded at startup) | Shared with backend |
| Native Plugin | 1-5ms | None (loaded at startup) | Shared with backend |
| MCP stdio | 50-200ms | 1-3s (subprocess spawn) | Separate process (~50-100MB) |
| MCP http | 100-500ms | N/A (already running) | None (remote) |
| T3 Client-Local | 200-2000ms | N/A (client already connected) | None (client-side) |

---

## File Quick Reference

| File | What It Contains |
|------|-----------------|
| `backend/app/tools/image_gen.py` | `generate_image`, `generate_rich_image` |
| `backend/app/tools/code_exec.py` | `execute_code`, `install_package` (E2B) |
| `backend/app/tools/cross_client.py` | `send_to_desktop`, `send_to_chrome`, `send_to_dashboard` (GenUI), `notify_client`, `list_connected_clients` |
| `backend/app/tools/search.py` | `google_search` (ADK Google Search grounding) |
| `backend/app/tools/rag.py` | `upload_document`, `search_documents` |
| `backend/app/tools/desktop_tools.py` | Desktop automation tools (not wired to agents yet) |
| `backend/app/plugins/notification_sender.py` | `send_notification`, `list_notification_channels` |
| `backend/app/services/plugin_registry.py` | 8 built-in MCP plugin manifests |
| `backend/app/services/e2b_service.py` | E2B sandbox lifecycle |
| `backend/app/agents/agent_factory.py` | Persona → tool wiring |
