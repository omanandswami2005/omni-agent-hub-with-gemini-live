# Unified Multi-Client Architecture — Omni Hub

> Production-grade, client-agnostic backend with T1/T2/T3 tool tiers,
> capability advertisement, and reverse-RPC for client-local tools.
>
> Combines: "Problem 1: Tool & MCP Discovery" + "Protocol-Ready Client-Agnostic Backend"

---

## 1. Design Principles

1. **One backend, many clients** — The server never hardcodes client-specific logic. Any client type connects via the same WebSocket protocol and advertises what it can do.
2. **Three tool tiers** — Backend-core (T1), backend-managed MCPs (T2), client-local (T3). The agent sees one flat list.
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

**T1** — Defined in `backend/app/tools/` as ADK `FunctionTool` instances. Always available. Assigned to personas via `agent_factory.py`.

**T2** — User toggles MCP servers on/off via the web dashboard. Config stored in Firestore (`{user_id, mcp_id, enabled}`). `MCPManager` lazily creates `McpToolset` instances with `StreamableHTTPConnectionParams` (remote) or `StdioConnectionParams` (local). Evicted on idle by the heartbeat reaper.

**T3** — Client advertises `local_tools` at auth handshake. Backend creates **ephemeral proxy tools** that route calls back to the client via WebSocket reverse-RPC. Tools vanish when client disconnects.

### 2.3 Agent Sees One Flat List

```
ToolRegistry.build_for_session(user_id) →
  T1: search, image_gen, code_exec, rag, cross_client_action
  T2: github_create_issue, github_list_repos       ← user toggled ON
  T3: write_file, brave_search_local               ← desktop connected
      send_sms, take_photo, get_location           ← mobile connected
```

The agent doesn't know tiers exist(but it should know actually, as user is gonna interact with agent with voice or text, and if asked what my desktop client do then agent should call a get capability or like this tool for that perticular device , wharever that device has advertised). The routing layer decides where each call goes.

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
    """Assembles the final tool list for an agent session."""

    def build_for_session(self, user_id: str) -> list[BaseTool]:
        tools = []

        # T1 — Core backend tools (always)
        tools.extend(get_core_tools(persona_id))

        # T2 — User-enabled MCPs
        mcp_mgr = get_mcp_manager()
        tools.extend(mcp_mgr.get_tools(user_id))

        # T3 — Client-local tools (from ConnectionManager capabilities)
        cm = get_connection_manager()
        for client_type, capabilities in cm.get_capabilities(user_id).items():
            for tool_def in capabilities.get("local_tools", []):
                tools.append(_create_proxy_tool(tool_def, user_id, client_type))

        return tools
```

---

## 6. ConnectionManager Extensions

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

## 7. WebSocket Message Protocol (Unified)

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

## 8. Cross-Client Action System

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

## 9. Client Types for Hackathon Presentation

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

## 10. Data Flow Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                          BACKEND (Cloud Run)                          │
│                                                                        │
│  ┌───────────────┐  ┌──────────────────┐  ┌─────────────────────────┐ │
│  │ ToolRegistry  │  │ ConnectionManager│  │    MCPManager           │ │
│  │               │  │                  │  │                         │ │
│  │ build_for_    │  │ { user_id:       │  │ { user_id:              │ │
│  │  session()    │──│   { web: ws,     │  │   { github: toolset,    │ │
│  │               │  │     desktop: ws, │  │     playwright: ... }   │ │
│  │ T1 + T2 + T3 │  │     mobile: ws } │  │ }                       │ │
│  └───────┬───────┘  │ }                │  └─────────────────────────┘ │
│          │          │                  │                               │
│          │          │ capabilities:    │                               │
│          │          │ { desktop:       │                               │
│          │          │   [write_file],  │                               │
│          │          │   mobile:        │                               │
│          │          │   [send_sms] }   │                               │
│          │          └────────┬─────────┘                               │
│          │                   │                                         │
│          └─────┐    ┌───────┘                                         │
│                │    │                                                  │
│                ▼    ▼                                                  │
│         ┌─────────────────┐                                           │
│         │   ADK Runner    │ ← Agent sees ONE flat tool list           │
│         │  run_live() /   │                                           │
│         │  run_async()    │                                           │
│         └────────┬────────┘                                           │
│                  │                                                     │
│    ┌─────────────┼──────────────┬──────────────┐                      │
│    │             │              │              │                      │
│    ▼             ▼              ▼              ▼                      │
│  T1 exec      T2 exec       T3 route       T3 route                 │
│  (local)      (MCP RPC)     → desktop WS    → mobile WS             │
│                                                                        │
└──────────┬─────────┬────────────┬──────────────┬──────────────────────┘
           │         │            │              │
           ▼         ▼            ▼              ▼
       ┌───────┐ ┌────────┐ ┌─────────┐   ┌──────────┐
       │  Web  │ │ Chrome │ │Desktop  │   │  Mobile  │
       │ Dash  │ │  Ext   │ │Electron │   │ Capacitor│
       └───────┘ └────────┘ └─────────┘   └──────────┘
```

---

## 11. Implementation Phases

### Phase 1: Hackathon MVP (Current → March 17)

- [x] `ConnectionManager` with per-user, per-client-type tracking
- [x] `ClientType` enum with web, desktop, chrome, mobile, glasses
- [x] `send_to_user()` broadcast + `send_to_client()` targeted
- [x] Heartbeat reaper
- [x] `cross_client_action` tool
- [x] `EventBus` for multi-client event distribution
- [ ] Extend auth handshake with `capabilities` + `local_tools`
- [ ] Implement `store_capabilities()` in ConnectionManager
- [ ] Build T3 proxy tool factory
- [ ] CLI client (100-line Python script)
- [ ] Show 3+ clients in demo

### Phase 2: Production (Post-Hackathon)

- [ ] Hard-gating in ToolRegistry (filter tools per-session based on capabilities)
- [ ] `capability_update` WS message for dynamic permissions
- [ ] Firestore persistence for T3 tool definitions (remember what desktop offers)
- [ ] Tool call analytics & routing metrics
- [ ] Formal OpenAPI spec for the WS protocol
- [ ] VS Code extension client
- [ ] Mobile (Capacitor) client with phone-native tools
- [ ] Rate limiting per-user tool calls

### Phase 3: Scale

- [ ] Multi-region with Cloud Run + Firestore global
- [ ] Session handoff between clients (start on phone, continue on desktop)
- [ ] Client capability negotiation (version compatibility)
- [ ] Tool marketplace (community-contributed T2 MCPs)
- [ ] Client SDK (npm/pip package for building new clients)

---

## 12. Security Considerations

| Concern | Mitigation |
|---|---|
| **T3 tool injection** | Validate tool definitions against schema; reject tools with dangerous names (`eval`, `exec`, `rm`) |
| **Tool call authorization** | Each T3 call includes the `call_id`; client must respond with matching `call_id` |
| **Client impersonation** | JWT validation on every WebSocket, not just HTTP upgrade |
| **Tool output sanitization** | T3 results are treated as untrusted input; agent system prompt warns about this |
| **Capability spoofing** | Capabilities are advisory; actual execution happens client-side. Spoofing capabilities just means the agent will try to call tools that fail |
| **Rate limiting** | Per-user tool call rate limits prevent abuse via T3 proxy tools |

---

## 13. Summary

The unified architecture combines three design patterns into one coherent system:

1. **Tool tiering** (T1/T2/T3) — Every tool has a home, clear lifecycle, and routing path
2. **Capability advertisement** — Clients declare what they can do; the backend adapts
3. **Reverse-RPC** — Client-local tools are first-class agent tools, no client-specific backend code

The result: **one backend, unlimited client types, one conversation**. A new client (smart fridge, car, VR headset) just connects, advertises capabilities, and the agent immediately knows how to use it.
