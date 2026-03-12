# Unified Multi-Client Architecture — Omni Hub

> Production-grade, client-agnostic backend with T1/T2/T3 tool tiers,
> capability advertisement, and reverse-RPC for client-local tools.
>
> Combines: "Problem 1: Tool & MCP Discovery" + "Protocol-Ready Client-Agnostic Backend"

---

## 1. Design Principles

1. **One backend, many clients** — The server never hardcodes client-specific logic. Any client type connects via the same WebSocket protocol and advertises what it can do.
2. **Three tool tiers** — Backend-core (T1), backend-managed plugins (T2), client-local (T3). Tools are distributed per-persona by capability-tag matching — each persona only sees tools relevant to its declared capabilities.
3. **Capability-driven** — Tools are gated by what's actually available, not by client type labels. An ESP32 that advertises `audio_capture` gets the same treatment as a desktop that advertises it.
4. **Soft-gate first, hard-gate later** — Phase 1: all tools registered, runtime error if client not connected. Phase 2: ToolRegistry filters per-session.
5. **Zero backend changes for new clients** — Adding a smart TV or car client means deploying a new client app. The backend adapts automatically based on advertised capabilities.

---

## 2. Tool Tier Architecture

### 2.1 The Three Tiers

| Tier | Where | Who Manages | Backend Awareness | Examples |
|---|---|---|---|---|
| **T1 — Core Backend** | Cloud Run | Hardcoded | Always | `search`, `image_gen`, `code_exec`, `rag`, `cross_client` |
| **T2 — Backend MCPs** | Cloud Run process | User (dashboard toggle) | Yes (Firestore) | `github`, `playwright`, `spotify`, `slack` |
| **T3 — Client-Local** | On device | User (local install) | Advertised at connect | `write_file`, `send_sms`, `capture_screen`, `brave_search_local` |

### 2.2 How Each Tier Is Managed

**T1** — Defined in `backend/app/tools/` as ADK `FunctionTool` instances. Always available. Assigned to personas via **capability-based matching** in `agent_factory.py` — a `T1_TOOL_REGISTRY` maps `ToolCapability` tags (search, code_execution, media) to tool factories, and each persona's `capabilities` list determines which T1 tools it receives.

**T2** — Managed by the **PluginRegistry** (`app/services/plugin_registry.py`). User toggles plugins on/off via the dashboard. The registry supports five plugin kinds:

| Kind | Transport | Example |
|---|---|---|
| `mcp_stdio` | ADK `McpToolset` + `StdioConnectionParams` (subprocess) | GitHub, Brave Search, Filesystem |
| `mcp_http` | ADK `McpToolset` + `StreamableHTTPConnectionParams` (remote) | Any remote MCP server |
| `mcp_oauth` | ADK `McpToolset` + `StreamableHTTPConnectionParams` + OAuth 2.0 Bearer token | Notion (official), any OAuth-secured remote MCP |
| `native` | Python module exporting `list[FunctionTool]` | Notification sender, custom integrations |
| `e2b` | E2B `AsyncSandbox` via `e2b_service.py` | Sandboxed code execution |

Plugins auto-discovered from `app/plugins/` at startup. MCP toolsets are lazily created per-user and evicted after 30 min idle.

> **OAuth MCP flow**: The `OAuthService` (`app/services/oauth_service.py`) implements RFC 9470 (Protected Resource Metadata) → RFC 8414 (Authorization Server Metadata) → RFC 7591 (Dynamic Client Registration) → RFC 7636 (PKCE S256) → Authorization Code → Token Exchange → Refresh. Users click "Connect with OAuth" in the UI → popup redirects to the provider → callback exchanges code for tokens → Bearer header injected into `StreamableHTTPConnectionParams.headers`.
>
> **Alternative auth methods**: For MCP servers that use static API keys instead of OAuth (e.g., community `npx`-based servers), use `mcp_stdio` or `mcp_http` with `env_keys` and `requires_auth: true` — the user provides secrets via the dashboard, and the registry injects them as environment variables at spawn time.

**T3** — Client advertises `local_tools` at auth handshake. Backend creates **ephemeral proxy tools** that route calls back to the client via WebSocket reverse-RPC. Tools vanish when client disconnects.

### 2.3 Per-Persona Tool Distribution (Capability-Based)

Tools are **no longer a flat list**. `ToolRegistry.build_for_session(user_id, personas)` returns a `dict[str, list]` keyed by persona_id. Each persona only receives T2 tools whose plugin `tags` overlap with the persona's `capabilities`.

```
ToolRegistry.build_for_session(user_id, personas) → {
  "assistant": [rag_tools, notification_tools]         ← tags∩caps: knowledge, communication
  "coder":     [e2b_tools, github_tools, filesystem]   ← tags∩caps: code_execution, sandbox
  "researcher":[wikipedia_tools, brave_search_tools]    ← tags∩caps: search, knowledge
  "analyst":   [e2b_tools]                              ← tags∩caps: code_execution, sandbox
  "creative":  []                                       ← no matching T2 plugins
  "__device__":[write_file, capture_screen]             ← T3 proxy tools for device_agent
}
```

T3 tools go to a dedicated **device_agent** (cross-client orchestrator) rather than polluting every persona.

#### ToolCapability Enum

Both plugins and personas declare capabilities from the same vocabulary:

```python
class ToolCapability(StrEnum):
    SEARCH = "search"           # Web search, knowledge retrieval
    CODE_EXECUTION = "code_execution"  # Running code, sandboxes
    KNOWLEDGE = "knowledge"     # RAG, documents, encyclopedias
    CREATIVE = "creative"       # Writing, brainstorming
    COMMUNICATION = "communication"  # Notifications, messaging
    WEB = "web"                 # Browser automation, web access
    SANDBOX = "sandbox"         # File system, isolated execution
    DATA = "data"               # Analytics, datasets
    MEDIA = "media"             # Image generation, multimedia
    DEVICE = "device"           # Cross-client / OS-level tools
    WILDCARD = "*"              # Matches ALL personas
```

Plugins declare `tags` in their manifest; personas declare `capabilities` in their config. Matching is `set(manifest.tags) & set(persona.capabilities)` — if the intersection is non-empty, the plugin's tools go to that persona.

---

## 3. Capability Advertisement Protocol

### 3.1 Auth Handshake (Extended)

Every client sends this on WebSocket connect:

```json
{
  "type": "auth",
  "token": "<firebase-jwt>",
  "client_type": "desktop",
  "capabilities": ["write_file", "read_file", "capture_screen", "run_command"],
  "local_tools": [
    {
      "name": "write_file",
      "description": "Write content to a file on the user's desktop",
      "parameters": {
        "path": { "type": "string", "description": "Absolute file path" },
        "content": { "type": "string", "description": "File content" }
      }
    },
    {
      "name": "brave_search_local",
      "description": "Search the web via local Brave MCP",
      "parameters": {
        "query": { "type": "string" }
      }
    }
  ]
}
```

| Field | Required | Description |
|---|---|---|
| `token` | Yes | Firebase JWT |
| `client_type` | Yes | `web` \| `desktop` \| `chrome` \| `mobile` \| `glasses` \| `tv` \| `car` \| `cli` \| `iot` \| `vscode` |
| `capabilities` | No | Array of capability strings this client supports |
| `local_tools` | No | Array of tool definitions (name, description, parameters) |

### 3.2 Server Response

```json
{
  "type": "auth_response",
  "status": "ok",
  "user_id": "abc123",
  "session_id": "abc123_desktop",
  "available_tools": ["search", "image_gen", "code_exec", "write_file", "brave_search_local"],
  "other_clients_online": ["web", "mobile"]
}
```

### 3.3 Dynamic Capability Update

Clients can update capabilities mid-session (e.g., user grants camera permission on mobile):

```json
{
  "type": "capability_update",
  "added": ["camera", "take_photo"],
  "removed": []
}
```

Backend updates `ConnectionManager` capabilities and rebuilds the tool set if hard-gating is active.

---

## 4. Reverse-RPC: Client-Local Tool Execution (T3)

### 4.1 Flow

```
Agent calls write_file(path="/tmp/hello.txt", content="Hello")
  ↓
ToolRegistry routes to T3 proxy tool (target: desktop)
  ↓
Backend sends to desktop client:
  {"type": "tool_invocation", "call_id": "xyz", "tool": "write_file", "args": {"path": "/tmp/hello.txt", "content": "Hello"}}
  ↓
Desktop executes locally (or forwards to its local MCP)
  ↓
Desktop responds:
  {"type": "tool_result", "call_id": "xyz", "result": {"success": true, "path": "/tmp/hello.txt"}}
  ↓
Backend returns result to agent
```

### 4.2 Timeout & Error Handling

| Scenario | Behavior |
|---|---|
| Client responds within 30s | Return result to agent |
| Client doesn't respond in 30s | Return `{"error": "Client timeout — desktop did not respond"}` |
| Client disconnects mid-call | Return `{"error": "Client disconnected during tool execution"}` |
| Client returns error | Forward error to agent as tool result |

### 4.3 Proxy Tool Factory

```python
def _create_proxy_tool(tool_def: dict, user_id: str, client_type: ClientType) -> FunctionTool:
    """Create an ephemeral proxy tool that routes calls to a connected client."""

    async def proxy_fn(**kwargs):
        cm = get_connection_manager()
        if not cm.is_online(user_id, client_type):
            return f"Error: {client_type} client is not connected."

        call_id = uuid4().hex
        invocation = {
            "type": "tool_invocation",
            "call_id": call_id,
            "tool": tool_def["name"],
            "args": kwargs,
        }
        # Send to specific client and await result via pending_results queue
        await cm.send_to_client(user_id, client_type, json.dumps(invocation))
        result = await _await_tool_result(user_id, call_id, timeout=30)
        return result

    proxy_fn.__name__ = tool_def["name"]
    proxy_fn.__doc__ = tool_def.get("description", "")
    return FunctionTool(proxy_fn)
```

---

## 5. ToolRegistry — Central Orchestrator

```python
class ToolRegistry:
    """Assembles per-persona tool dicts for an agent session."""

    async def build_for_session(
        self, user_id: str, personas: list[PersonaResponse] | None = None,
    ) -> dict[str, list]:
        plugin_registry = get_plugin_registry()

        # Collect T2 tools per enabled plugin
        plugin_tools: dict[str, list] = {}  # plugin_id → tools
        for plugin_id in plugin_registry.get_enabled_ids(user_id):
            manifest = plugin_registry.get_manifest(plugin_id)
            plugin_tools[plugin_id] = await plugin_registry._get_plugin_tools(...)

        # Distribute T2 tools to personas by tag matching
        result: dict[str, list] = {}
        for persona in personas:
            matched = []
            pcaps = set(persona.capabilities)
            for plugin_id, tools in plugin_tools.items():
                ptags = set(plugin_registry.get_manifest(plugin_id).tags)
                if "*" in ptags or ptags & pcaps:  # wildcard or intersection
                    matched.extend(tools)
            result[persona.id] = matched

        # T3 proxy tools → __device__ key (for cross-client orchestrator)
        cm = get_connection_manager()
        device_tools = []
        for ct, cap_data in cm.get_capabilities(user_id).items():
            for tool_def in cap_data.get("local_tools", []):
                device_tools.append(_create_proxy_tool(tool_def, user_id, ct))
        if device_tools:
            result["__device__"] = device_tools

        return result
```

---

## 6. Plugin Architecture — T2 Deep Dive

The **PluginRegistry** (`app/services/plugin_registry.py`) is the unified lifecycle manager for all T2 plugins. It replaces the old `MCPManager` with a scalable, pluggable system that any developer can extend independently.

### 6.1 Plugin Manifest

Every plugin is described by a `PluginManifest` — a self-contained configuration:

```python
class PluginManifest(BaseModel):
    id: str                              # Unique identifier
    name: str                            # Display name
    description: str                     # One-line description
    category: PluginCategory             # search, dev, productivity, etc.
    kind: PluginKind                     # mcp_stdio | mcp_http | mcp_oauth | native | e2b

    # MCP_STDIO fields
    command: str = ""                    # e.g. "python", "npx"
    args: list[str] = []                 # e.g. ["scripts/local_mcp_server.py"]
    env_keys: list[str] = []             # Required env vars / secrets

    # MCP_HTTP fields
    url: str = ""                        # StreamableHTTP endpoint

    # Native plugin fields
    module: str = ""                     # e.g. "app.plugins.telegram_notify"
    factory: str = "get_tools"           # Function returning list[FunctionTool]

    # Behaviour
    lazy: bool = True                    # Load tools only when user activates
    requires_auth: bool = False          # User must provide API keys first
    max_context_tokens: int = 0          # Context budget per turn (0 = unlimited)
    tools_summary: list[ToolSummary] = []  # Pre-declared lightweight summaries
```

### 6.2 Plugin Lifecycle

```
           ┌──────────┐
           │ AVAILABLE │ ← In catalog, not enabled
           └────┬─────┘
                │ user toggles ON
                ▼
           ┌──────────┐
           │ ENABLED   │ ← Marked active, toolset not connected yet
           └────┬─────┘
                │ first tool access / lazy connect
                ▼
           ┌──────────┐
           │ CONNECTED │ ← Toolset active, tools discovered
           └────┬─────┘
                │ error / disconnect
                ▼
           ┌──────────┐
           │  ERROR    │ → retry on next access
           └──────────┘
```

**MCP lifecycle via ADK:**
```python
# 1. Create toolset (ADK handles subprocess/HTTP lifecycle)
toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["scripts/local_mcp_server.py"],
        )
    )
)

# 2. Discover tools (validates connection)
tools = await toolset.get_tools()  # Returns list of ADK-compatible tools

# 3. Call tools (ADK routes to MCP server transparently)
result = await echo_tool.run_async(args={"message": "hello"}, tool_context=None)

# 4. Close (ADK cleans up subprocess/connection)
await toolset.close()
```

### 6.3 Plugin Kinds

**MCP Stdio** — Spawns a subprocess that speaks MCP protocol over stdin/stdout. ADK manages the process lifecycle. Best for local tools.
```python
# Uses: python, npx, uvx, node, etc.
PluginManifest(kind=PluginKind.MCP_STDIO, command="python", args=["server.py"])
```

**MCP HTTP** — Connects to a remote MCP server via StreamableHTTP. No subprocess needed.
```python
PluginManifest(kind=PluginKind.MCP_HTTP, url="https://mcp-server.example.com/mcp")
```

**Native** — A Python module in `app/plugins/` that exports ADK `FunctionTool` instances. Zero network overhead.
```python
PluginManifest(kind=PluginKind.NATIVE, module="app.plugins.telegram_notify", factory="get_tools")
```

**MCP OAuth** — Connects to a remote MCP server that requires OAuth 2.0 authorization. The backend handles the full OAuth flow (discovery, PKCE, dynamic client registration, token exchange, refresh) and injects a Bearer token into the HTTP connection.
```python
PluginManifest(kind=PluginKind.MCP_OAUTH, url="https://mcp.notion.com/mcp",
               oauth=OAuthConfig(client_name="Omni Hub"))
```

**E2B** — Special built-in for sandboxed code execution via E2B cloud.
```python
PluginManifest(kind=PluginKind.E2B)  # Always e2b-sandbox
```

> **Choosing between `mcp_http` and `mcp_oauth`**: If the remote MCP server uses static API keys or no auth, use `mcp_http` with `env_keys`. If it implements the MCP OAuth spec (RFC 9470 + RFC 8414 + RFC 7591), use `mcp_oauth` for automatic token management. Both use `StreamableHTTPConnectionParams` under the hood.

### 6.4 Auto-Discovery

Developers add plugins by placing a Python file in `app/plugins/` with a `MANIFEST` attribute:

```python
# app/plugins/telegram_notify.py
from google.adk.tools import FunctionTool
from app.models.plugin import PluginManifest, PluginKind, PluginCategory

async def send_telegram(chat_id: str, message: str) -> str:
    """Send a Telegram message to a user or group."""
    # ... implementation ...
    return f"Message sent to {chat_id}"

def get_tools() -> list[FunctionTool]:
    return [FunctionTool(send_telegram)]

MANIFEST = PluginManifest(
    id="telegram-notify",
    name="Telegram Notifications",
    description="Send messages via Telegram Bot API.",
    category=PluginCategory.COMMUNICATION,
    kind=PluginKind.NATIVE,
    module="app.plugins.telegram_notify",
    factory="get_tools",
    env_keys=["TELEGRAM_BOT_TOKEN"],
    requires_auth=True,
)
```

At startup, `PluginRegistry._discover_plugin_modules()` scans `app/plugins/*.py`, imports each module, and registers any `PluginManifest` it finds. **No other backend code needs to change.**

### 6.5 Lazy Tool Loading — On-Demand Strategy

To keep the agent's context window lean:

1. **Summaries first** — Agent receives `ToolSummary` (name + one-line description) for every enabled plugin. This is ~20 tokens per tool.
2. **Schemas on demand** — When the user asks for a specific capability, the API returns full `ToolSchema` (name + description + JSON Schema parameters). The agent then has everything to make the call.
3. **Context budget** — Each plugin can declare `max_context_tokens` to cap how much context its tools consume per turn.

```
┌─────────────────────────────────────────────────────────────────┐
│ Agent System Prompt (always)                                    │
│                                                                 │
│ You have access to these plugins:                              │
│   - E2B Sandbox: execute_code, install_package                 │  ← summaries only
│   - GitHub: github_create_issue, github_list_repos             │     (~20 tokens each)
│   - Telegram: send_telegram                                    │
│                                                                 │
│ When the user asks to use a plugin, call its tools directly.   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ On-demand schema load (only when needed)                        │
│                                                                 │
│ GET /api/v1/plugins/github/tools                               │
│ → [{name: "create_issue", params: {title: str, body: str}},   │
│    {name: "list_repos", params: {org: str, page: int}}]        │
└─────────────────────────────────────────────────────────────────┘
```

### 6.6 Plugin API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/plugins/catalog` | Full catalog with per-user state |
| `GET` | `/api/v1/plugins/enabled` | List of enabled plugin IDs |
| `POST` | `/api/v1/plugins/toggle` | Enable/disable a plugin |
| `POST` | `/api/v1/plugins/secrets` | Set user API keys for a plugin |
| `GET` | `/api/v1/plugins/summaries` | Lightweight tool summaries (for agent) |
| `GET` | `/api/v1/plugins/{id}/tools` | Full tool schemas (on-demand) |
| `GET` | `/api/v1/plugins/{id}` | Plugin detail |

### 6.7 Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                     PluginRegistry                            │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │  Built-in    │  │ Auto-       │  │   Runtime             │ │
│  │  Catalog     │  │ Discovered  │  │   Registered          │ │
│  │  (8 plugins) │  │ app/plugins/│  │   (API)               │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬───────────┘ │
│         └────────────────┼─────────────────────┘             │
│                          ▼                                    │
│                   ┌──────────────┐                            │
│                   │  _catalog    │  { id → PluginManifest }  │
│                   └──────┬───────┘                            │
│                          │                                    │
│            ┌─────────────┼──────────────┐                    │
│            ▼             ▼              ▼                     │
│     ┌──────────┐  ┌──────────┐  ┌──────────────┐            │
│     │MCP Stdio │  │MCP HTTP  │  │Native Module │            │
│     │McpToolset│  │McpToolset│  │FunctionTool[]│            │
│     │(per user)│  │(per user)│  │  (shared)    │            │
│     └────┬─────┘  └────┬─────┘  └──────┬───────┘            │
│          └──────────────┼───────────────┘                    │
│                         ▼                                     │
│                 ┌───────────────┐                             │
│                 │  get_tools()  │ → list[ADK BaseTool]       │
│                 └───────────────┘                             │
└──────────────────────────────────────────────────────────────┘
```

---

## 7. ConnectionManager Extensions

### Current State (Already Implemented)

The existing `ConnectionManager` already supports:
- Per-user, per-client-type registration (`{ user_id: { client_type: (ws, connected_at, os_name) } }`)
- `send_to_user()` — broadcast to all clients
- `send_to_client()` — target specific devices
- `get_connected_clients()` — list online devices
- `get_other_clients_online()` — cross-client awareness
- Heartbeat reaper with ping/evict cycle

### Needed Extensions

| Extension | Purpose |
|---|---|
| `store_capabilities(user_id, client_type, capabilities, local_tools)` | Store advertised capabilities at connect |
| `get_capabilities(user_id) → dict[ClientType, dict]` | Return capabilities for all connected clients |
| `update_capabilities(user_id, client_type, added, removed)` | Handle mid-session capability changes |
| Capability cleanup on disconnect | Remove T3 proxy tools when client disconnects |

---

## 8. WebSocket Message Protocol (Unified)

### Client → Server Messages

| Type | When | Key Fields |
|---|---|---|
| `auth` | On connect | `token`, `client_type`, `capabilities`, `local_tools` |
| `capability_update` | Mid-session | `added[]`, `removed[]` |
| `text` | User types a message | `content` |
| `image` | User sends an image | `image_base64`, `mime_type` |
| `persona_switch` | Change persona | `persona_id` |
| `mcp_toggle` | Toggle MCP plugin | `mcp_id`, `enabled` |
| `tool_result` | T3 reverse-RPC response | `call_id`, `result` |
| `control` | Pause/resume/end | `action` |
| Binary frame | PCM-16 audio | Raw bytes (16kHz 16-bit) |

### Server → Client Messages

| Type | When | Key Fields |
|---|---|---|
| `auth_response` | After auth | `status`, `user_id`, `session_id`, `available_tools`, `other_clients_online` |
| `response` | Agent text/GenUI | `content_type`, `data`, `genui` |
| `transcription` | Voice transcript | `text`, `direction`, `finished` |
| `image_response` | Generated image | `tool_name`, `image_base64`/`parts` |
| `tool_call` | Agent invokes a tool | `tool_name`, `arguments`, `status` |
| `tool_response` | Tool execution result | `tool_name`, `result`, `success` |
| `tool_invocation` | T3 reverse-RPC request | `call_id`, `tool`, `args` |
| `agent_activity` | Transparency events | `activity_type`, `title`, `details`, `status` |
| `status` | State changes | `state` (idle/listening/processing/speaking) |
| `cross_client` | Cross-device action | `target_client`, `action`, `payload` |
| `connected` | Client announcement | `client_type`, `user_id` |
| `persona_changed` | Persona switch confirmed | `persona_id` |
| `error` | Error | `message`, `code` |
| `ping` | Heartbeat | — |
| Binary frame | PCM-24 audio | Raw bytes (24kHz 16-bit) |

---

## 9. Cross-Client Action System

The `cross_client_action` tool lets the agent coordinate across connected devices:

```python
async def cross_client_action(
    target_client: str,
    action: str,
    payload: dict,
    tool_context: ToolContext | None = None,
) -> str:
    """Send an action to a specific connected client.

    Examples:
    - target="desktop", action="open_file", payload={"path": "/code/main.py"}
    - target="mobile", action="show_notification", payload={"title": "Done!", "body": "Build complete"}
    - target="chrome", action="open_tab", payload={"url": "https://github.com/..."}
    """
```

**Cross-client scenarios:**
- "Show this code on my desktop" → `target=desktop, action=open_file`
- "Send this to my phone" → `target=mobile, action=show_notification`
- "Open that link in my browser" → `target=chrome, action=open_tab`
- "Display this on the TV" → `target=tv, action=show_dashboard`

---

## 10. Client Types for Hackathon Presentation

### Currently Implemented

| Client | Type | Transport | Status |
|---|---|---|---|
| **Web Dashboard** | `web` | WebSocket `/ws/live` | ✅ Full — voice + text + GenUI + images |
| **Desktop (Electron)** | `desktop` | WebSocket `/ws/live` | ✅ Scaffold — tray app, persistent connection |
| **Chrome Extension** | `chrome` | WebSocket `/ws/live` | ✅ Scaffold — popup + background service worker |

### Suggested Additional Clients (Hackathon Demo)

| Client | Type | Transport | Demo Value | Effort |
|---|---|---|---|---|
| **CLI / Terminal** | `cli` | WebSocket | Text-only agent in your terminal. Shows "no UI needed" story. | Low — Python/Node script, 100 lines |
| **VS Code Extension** | `vscode` | WebSocket | Copilot-like sidebar powered by your own agent. Cross-client: "open this file on desktop" | Medium — Extension API + webview panel |
| **Mobile (Capacitor/PWA)** | `mobile` | WebSocket | Voice-first on phone. Phone-specific tools: `send_sms`, `get_location`, `take_photo` | Medium — Capacitor wraps dashboard |
| **Smart Display / Tablet Kiosk** | `tv` | WebSocket | Dashboard-only view for ambient monitoring. Agent pushes GenUI, device just renders. | Low — stripped-down web view, read-only |
| **IoT / ESP32** | `iot` | WebSocket | Tiny device that receives commands: `set_led_color`, `read_sensor`. Wow factor for hardware demos. | Medium — Arduino/MicroPython + WiFi |
| **Smart Glasses (Web-based)** | `glasses` | WebSocket | Minimal HUD: text transcription overlay + voice input. Shows futuristic UX. | Low — simple HTML page with AR framing |
| **Car Infotainment** | `car` | WebSocket | Android Auto / CarPlay mockup. Voice-only + large-button GenUI. | Low — themed web view |
| **Slack / Discord Bot** | `bot` | REST → WS bridge | Agent available in team chat. Shows "enterprise integration" story. | Medium — Bot SDK + WebSocket bridge |
| **Smartwatch (WearOS/watchOS)** | `watch` | WebSocket via companion | Voice input + haptic output. Ultra-minimal UI. | High — platform-specific |

### Recommended Demo Set (Maximum Impact, Minimum Effort)

For a 5-minute hackathon demo, show **4 clients simultaneously**:

1. **Web Dashboard** (primary) — Full experience: voice, text, GenUI, images
2. **CLI Terminal** — "Same agent, no GUI" — type a question, get answer
3. **Desktop Electron** — File system tools: "Save this code to my desktop"
4. **Chrome Extension** — "Summarize this page" on any website

**The story**: "One agent, one backend, four surfaces. The agent knows what each client can do and adapts. Ask it to save a file — it routes to desktop. Ask it to summarize a page — it routes to Chrome. All through the same conversation."

---

## 11. Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          BACKEND (Cloud Run)                            │
│                                                                          │
│  ┌───────────────┐  ┌──────────────────┐  ┌───────────────────────────┐ │
│  │ ToolRegistry  │  │ ConnectionManager│  │     PluginRegistry        │ │
│  │               │  │                  │  │                           │ │
│  │ build_for_    │  │ { user_id:       │  │ MCP Stdio (McpToolset)    │ │
│  │  session()    │──│   { web: ws,     │  │ MCP HTTP  (McpToolset)    │ │
│  │               │  │     desktop: ws, │  │ Native    (FunctionTool)  │ │
│  │ T1 + T2 + T3 │  │     mobile: ws } │  │ E2B       (AsyncSandbox)  │ │
│  └───────┬───────┘  │ }                │  └───────────────────────────┘ │
│          │          │                  │                                 │
│          │          │ capabilities:    │  ┌───────────────────────────┐ │
│          │          │ { desktop:       │  │     app/plugins/          │ │
│          │          │   [write_file],  │  │  Auto-discovered modules  │ │
│          │          │   mobile:        │  │  (MANIFEST attribute)     │ │
│          │          │   [send_sms] }   │  └───────────────────────────┘ │
│          │          └────────┬─────────┘                                 │
│          │                   │                                           │
│          └─────┐    ┌───────┘                                           │
│                │    │                                                    │
│                ▼    ▼                                                    │
│         ┌─────────────────┐                                             │
│         │   ADK Runner    │ ← Agent sees ONE flat tool list             │
│         │  run_live() /   │    (summaries first, schemas on demand)     │
│         │  run_async()    │                                             │
│         └────────┬────────┘                                             │
│                  │                                                       │
│    ┌─────────────┼──────────────┬──────────────┐                        │
│    │             │              │              │                        │
│    ▼             ▼              ▼              ▼                        │
│  T1 exec      T2 plugin     T3 route       T3 route                   │
│  (local)      (MCP/Native/  → desktop WS    → mobile WS               │
│               E2B)                                                      │
│                                                                          │
└──────────┬─────────┬────────────┬──────────────┬────────────────────────┘
           │         │            │              │
           ▼         ▼            ▼              ▼
       ┌───────┐ ┌────────┐ ┌─────────┐   ┌──────────┐
       │  Web  │ │ Chrome │ │Desktop  │   │  Mobile  │
       │ Dash  │ │  Ext   │ │Electron │   │ Capacitor│
       └───────┘ └────────┘ └─────────┘   └──────────┘
```

---

## 12. Implementation Phases

### Phase 1: Hackathon MVP (Current → March 17)

- [x] `ConnectionManager` with per-user, per-client-type tracking
- [x] `ClientType` enum with web, desktop, chrome, mobile, glasses
- [x] `send_to_user()` broadcast + `send_to_client()` targeted
- [x] Heartbeat reaper
- [x] `cross_client_action` tool
- [x] `EventBus` for multi-client event distribution
- [x] **PluginRegistry** — unified plugin lifecycle manager (MCP + native + E2B)
- [x] **Plugin manifest system** — `PluginManifest` with 5 kinds (mcp_stdio, mcp_http, mcp_oauth, native, e2b), auto-discovery
- [x] **MCP via ADK** — `McpToolset` + `StdioConnectionParams` tested end-to-end
- [x] **Native plugin example** — `app/plugins/notification_sender.py`
- [x] **Lazy tool loading** — summaries first, schemas on demand
- [x] **Plugin API** — `/api/v1/plugins/` catalog, toggle, secrets, schemas, OAuth start/callback/disconnect
- [x] **MCPManager compat layer** — backward-compatible wrapper
- [x] **E2B sandbox** — tested with 5 real scenarios
- [x] **16 pytest tests** — plugin registry, MCP, native, lazy loading
- [x] Extend auth handshake with `capabilities` + `local_tools`
- [x] Implement `store_capabilities()` in ConnectionManager
- [x] Build T3 proxy tool factory
- [x] CLI client (100-line Python script)
- [x] Plugin developer template (`app/plugins/TEMPLATE.py`)
- [x] **Hardening audit (13 fixes)** — memory leak, race conditions, enum safety, timeouts, JSON validation
- [x] **54 pytest tests passing** — 29 tool registry + 16 plugin registry + 9 bug-fix verification
- [x] **OAuth MCP support** — `MCP_OAUTH` kind with full RFC 9470/8414/7591/7636 flow, Notion MCP verified
- [x] **3-layer agent architecture** — Root Router → Persona Pool + TaskArchitect + Device Agent
- [x] **Capability-based tool matching** — `ToolCapability` enum, persona `capabilities`, plugin `tags`
- [x] **Per-persona T2 distribution** — `build_for_session()` returns `dict[str, list]` not flat list
- [x] **Cross-client orchestrator** — `device_agent` sub-agent with T3 proxy tools
- [x] **TaskArchitect integration** — `plan_task` FunctionTool on root agent
- [ ] Show 3+ clients in demo

### Phase 2: Production (Post-Hackathon)

- [x] Hard-gating in ToolRegistry (per-persona T2 distribution via capability-tag matching)
- [ ] `capability_update` WS message for dynamic permissions
- [ ] Firestore persistence for plugin state & T3 tool definitions
- [ ] Tool call analytics & routing metrics
- [ ] Plugin marketplace (community-contributed plugins via registry)
- [ ] Formal OpenAPI spec for the WS protocol
- [ ] VS Code extension client
- [ ] Mobile (Capacitor) client with phone-native tools
- [ ] Rate limiting per-user tool calls
- [ ] Plugin health monitoring & auto-restart for failed MCP processes

### Phase 3: Scale

- [ ] Multi-region with Cloud Run + Firestore global
- [ ] Session handoff between clients (start on phone, continue on desktop)
- [ ] Client capability negotiation (version compatibility)
- [ ] Plugin sandboxing (resource limits per plugin)
- [ ] Client SDK (npm/pip package for building new clients)

---

## 13. Security Considerations

| Concern | Mitigation |
|---|---|
| **T3 tool injection** | Validate tool definitions against schema; reject tools with dangerous names (`eval`, `exec`, `rm`) |
| **Tool call authorization** | Each T3 call includes the `call_id`; client must respond with matching `call_id` |
| **Client impersonation** | JWT validation on every WebSocket, not just HTTP upgrade |
| **Tool output sanitization** | T3 results are treated as untrusted input; agent system prompt warns about this |
| **Capability spoofing** | Capabilities are advisory; actual execution happens client-side. Spoofing capabilities just means the agent will try to call tools that fail |
| **Rate limiting** | Per-user tool call rate limits prevent abuse via T3 proxy tools |

---

## 14. Summary

The unified architecture combines five design patterns into one coherent system:

1. **Tool tiering** (T1/T2/T3) — Every tool has a home, clear lifecycle, and routing path
2. **Plugin architecture** — Scalable, pluggable T2 system where any developer can create MCP servers, native modules, or E2B tools independently — just add a file to `app/plugins/`
3. **Capability advertisement** — Clients declare what they can do; the backend adapts
4. **Reverse-RPC** — Client-local tools are first-class agent tools, no client-specific backend code
5. **Capability-based tool matching** — Plugins declare `tags`, personas declare `capabilities`. The ToolRegistry distributes T2 tools per-persona using set intersection (`tags ∩ caps`). T3 tools go to a dedicated `device_agent`. No more flat tool lists.

**3-Layer Agent Architecture:**

| Layer | Agent(s) | Role |
|---|---|---|
| **Layer 0** | `omni_root` (Router) | Classifies intent, routes via `transfer_to_agent`, has `plan_task` tool |
| **Layer 1** | Persona Pool (assistant, coder, researcher, analyst, creative) | Capability-matched T1+T2 tools per persona |
| **Layer 2** | TaskArchitect (`plan_task` tool) | Decomposes complex tasks into multi-step plans |
| **Layer 3** | `device_agent` (Cross-Client Orchestrator) | Cross-client actions + T3 proxy tools |

The result: **one backend, unlimited client types, unlimited plugins, one conversation**. A new client just connects and advertises capabilities. A new plugin just drops a manifest file with `tags`. The agent immediately knows how to use everything — and each persona only gets tools relevant to its expertise.

---

## 15. Hardening Audit (March 12, 2026)

Systematic audit of all backend services for hackathon demo stability and multi-developer extensibility. All fixes have dedicated tests in `TestBugFixes`.

### 15.1 Critical Fixes

| # | Issue | File | Fix |
|---|---|---|---|
| 1 | **Memory leak** — `resolve_tool_result()` didn't clean up `_pending_results` after resolving | `tool_registry.py` | Changed `.get()` to `.pop()` so call_id is removed immediately |
| 2 | **Deprecated API** — `asyncio.get_event_loop()` emits warnings on Python 3.14 | `tool_registry.py` | Replaced with `asyncio.get_running_loop()` |
| 3 | **Race condition** — `_runner_cache` and `_chat_runner_cache` had no concurrency protection | `ws_live.py` | Added `asyncio.Lock` to both `_get_runner()` and `_get_chat_runner()` |
| 4 | **JSON injection** — `cross_client_action` payload forwarded LLM output without validation | `cross_client.py` | Added `_safe_parse_json()` — returns raw string on malformed JSON instead of crashing |
| 5 | **Unsafe enum** — `MCPCategory(value)` crashes on unknown category strings | `mcp_manager.py` | Added `_safe_category()` with try/except, defaults to `MCPCategory.OTHER` |

### 15.2 Reliability Fixes

| # | Issue | File | Fix |
|---|---|---|---|
| 6 | **Silent event drops** — Dashboard queue (256) too small for active sessions | `event_bus.py` | Increased `_DEFAULT_QUEUE_MAXSIZE` from 256 to 1024 |
| 7 | **Iteration mutation** — `_ping_all()` inner dict not copied before async iteration | `connection_manager.py` | Added `dict(user_conns)` copy before iterating |
| 8 | **No timeout** — Bootstrap `asyncio.gather()` waits forever if Firestore is slow | `init.py` | Wrapped in `asyncio.wait_for(..., timeout=10)` with graceful fallback |

### 15.3 Extensibility Fixes

| # | Issue | File | Fix |
|---|---|---|---|
| 9 | **Limited T3 types** — Proxy tool type map only had string/int/float/bool | `tool_registry.py` | Added `array → list` and `object → dict` |
| 10 | **No plugin template** — New developers had no starting point | `app/plugins/TEMPLATE.py` | Created documented template with MANIFEST schema, tool contract, and factory pattern |
| 11 | **Silent invalidation** — Runner cache invalidation logged nothing | `ws_live.py` | `invalidate_runner()` now logs whether live/chat runners were evicted |
| 12 | **Missing auth TODO** — Plugin toggle has no per-user ownership check | `plugins.py` | Added `.. todo::` docstring noting multi-tenant auth needed |
| 13 | **Template auto-load** — `TEMPLATE.py` would be auto-discovered as a real plugin | `plugin_registry.py` | Added `TEMPLATE.py` to the exclusion list in `_discover_plugin_modules()` |

### Key Files

| File | Purpose |
|---|---|
| `app/models/plugin.py` | Plugin manifest & state Pydantic schemas |
| `app/models/client.py` | ClientType enum (11 types) + ClientInfo |
| `app/models/ws_messages.py` | WS message schemas incl. T3 reverse-RPC messages |
| `app/services/plugin_registry.py` | Central plugin lifecycle manager (singleton) |
| `app/services/tool_registry.py` | T1+T2+T3 tool orchestrator + T3 proxy factory |
| `app/services/connection_manager.py` | WS registry with capability storage |
| `app/services/mcp_manager.py` | Backward-compatible wrapper → PluginRegistry |
| `app/api/plugins.py` | REST API for plugin catalog, toggle, schemas |
| `app/api/ws_live.py` | WS endpoints with extended auth + T3 handling |
| `app/plugins/__init__.py` | Auto-discovery package |
| `app/plugins/notification_sender.py` | Example native plugin |
| `scripts/local_mcp_server.py` | Test MCP server (FastMCP, stdio) |
| `cli/omni_cli.py` | CLI client — text-only agent in terminal |
| `tests/test_services/test_plugin_registry.py` | 16 pytest tests — plugin registry |
| `tests/test_services/test_tool_registry.py` | 38 pytest tests — capabilities, T3, ToolRegistry, bug-fix verification |
| `app/plugins/TEMPLATE.py` | Plugin developer template (excluded from auto-discovery) |
