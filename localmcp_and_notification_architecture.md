Good — these are genuinely two tangled design questions. Let me untangle both clearly.

---

## Problem 1: Tool & MCP Discovery Across All Client Types

### The Real Shape of the Problem

You have **3 fundamentally different tool tiers** that need to coexist:

| Tier | Where it lives | Who manages it | Backend knows it? |
|---|---|---|---|
| **T1 — Core backend tools** | Cloud Run | You (hardcoded) | Always |
| **T2 — Backend-managed MCPs** | Cloud Run process | User via web dashboard | Yes (Firestore config) |
| **T3 — Client-local tools/MCPs** | On the device | User locally | No — must be ADVERTISED |

The confusion comes from mixing T2 and T3. T2 is easy — it's just your existing MCPManager with a Firestore-backed config. T3 is the hard one.

### T3: Client Tool Advertisement

The client knows what it has. On connect, it tells the backend:

```json
{
  "type": "auth",
  "token": "...",
  "client_type": "desktop",
  "local_tools": [
    {
      "name": "write_file",
      "description": "Write content to a file on the user's desktop",
      "parameters": {
        "path": {"type": "string"},
        "content": {"type": "string"}
      }
    },
    {
      "name": "brave_search_local",   // ← this is a LOCAL MCP the user installed
      "description": "Search the web via local Brave MCP",
      "parameters": {"query": {"type": "string"}}
    }
  ]
}
```

The backend then creates **ephemeral proxy tools** that wrap each advertised tool:

```
When agent calls write_file(path, content):
  → Backend sends {"type": "tool_invocation", "tool": "write_file", "args": {...}} over WS to desktop
  → Desktop executes it locally (or forwards to its local MCP)
  → Desktop sends back {"type": "tool_result", "result": {...}}
  → Backend returns result to agent
```

This is a **reverse RPC** pattern. The client provides the execution, the backend just routes. When the desktop disconnects, those proxy tools vanish from the agent's tool list.

### Same for Android
Android client connects and advertises:
```json
"local_tools": [
  {"name": "send_sms", ...},
  {"name": "take_photo", ...},
  {"name": "get_location", ...}
]
```

### How the Agent Sees It — One Flat List

At session start, `ToolRegistry` assembles:

```
Final tool list for this session:
  T1: search, image_gen, code_exec, RAG          ← always
  T2: github, playwright                           ← user enabled via dashboard
  T3: write_file, brave_search_local              ← desktop is connected
       send_sms, take_photo                        ← android is also connected
```

The agent doesn't know or care which tier each tool is in. The routing layer decides WHERE each call goes (backend vs. which connected client).

### Data Flow Diagram

```
Web Dashboard (user plugin page)
  └─→ POST /api/v1/mcp/toggle → Firestore {user_id, mcp_id, enabled}
      └─→ MCPManager loads/unloads server-side MCP process    [T2]

Desktop Client auth handshake
  └─→ local_tools: [write_file, brave_search_local, ...]
      └─→ ConnectionManager.store_capabilities(user_id, tools)
          └─→ ToolRegistry builds ephemeral proxy tools        [T3]

Agent session starts
  └─→ ToolRegistry.build_for_session(user_id)
      └─→ T1 + T2 (from MCPManager) + T3 (from ConnectionManager)
```

---

## Problem 2: Notifications + Cron Jobs

### Why it's Confusing

You're mixing up two separate concepts:
1. **Scheduled actions** — "do X at time Y"
2. **Notification delivery** — "tell me about it via channel Z"

These should be independent. Not every scheduled action needs a notification. Not every notification comes from a scheduled action.

### Correct Mental Model

**A `ScheduledTask` has an optional `NotificationRule`:**

```
ScheduledTask
├── id
├── action           → what to actually DO  
├── schedule         → when (one-time or recurring)
└── notify_rule?     → optional: how/when to tell the user
    ├── channel      → "email" | "push" | "sms"
    ├── condition    → when to fire (always / on_result_condition)
    └── message      → template like "Your summary: {result.summary}"
```

### Voice Interaction Examples

**Example 1 — The reminder (task IS the notification):**
```
User: "Remind me of John's birthday on March 15"
→ ScheduledTask {
    action: "send_notification",
    schedule: "2026-03-15 09:00",
    message: "🎂 Today is John's birthday!"
  }
→ No separate notify_rule — the action itself IS the notification
```

**Example 2 — Task with result, user wants email:**
```
User: "Every Monday, fetch my portfolio and email me a summary"
→ ScheduledTask {
    action: "fetch_portfolio_and_summarize",
    schedule: "0 9 * * MON",
    notify_rule: {
      channel: "email",
      condition: "always",
      message: "Here's your weekly portfolio summary:\n{result.summary}"
    }
  }
```

**Example 3 — Task with conditional notification:**
```
User: "Check my server every 5 minutes, but only alert me if it's down"
→ ScheduledTask {
    action: "check_server_health",
    schedule: "*/5 * * * *",
    notify_rule: {
      channel: "email",
      condition: "result.status == 'error'",
      message: "⚠️ Server issue detected: {result.error}"
    }
  }
→ Runs silently every 5 min, email ONLY fires when condition is true
```

**Example 4 — Agent-triggered notification (no schedule):**
```
User: "Email me when the code execution finishes"
→ No cron needed — the execute_code tool's on_complete hook fires a notification
→ This is just a direct notification call, not a scheduled task
```

### Cloud Run vs Cloud Scheduler/Tasks

| Use case | Best option |
|---|---|
| **One-off, specific time** (birthday reminder, reminder in 2 hours) | **Cloud Tasks** — enqueue a task with a future ETA |
| **Recurring on a cron pattern** (every Monday, every 5 min) | **Cloud Scheduler** → triggers a Cloud Run endpoint |
| **Triggered by agent mid-conversation** (execute code then notify me) | **Direct call** — no scheduler needed |

Both Cloud Tasks and Cloud Scheduler just call your backend's `/internal/run-task/{task_id}` endpoint. Your backend then executes the action and optionally sends the notification.

### Courier Integration Design

User-managed, not you-managed:

```
User adds Courier API key in Settings (web dashboard)
  → Stored in Secret Manager under {user_id}/courier_api_key

When notification fires:
  → NotificationService.send(user_id, channel, message)
  → Loads correct key from Secret Manager
  → Calls Courier MCP / Resend API / etc.
```

This way YOUR backend code has zero hardcoded API keys. Each user brings their own Courier key. If they haven't set one, fallback to a default transport you control (e.g. your own SendGrid key for free-tier notifications, their key for custom channels).

---

## Clean Summary

**Tools:**
- T1 (backend tools) + T2 (backend MCPs via dashboard) = already exists, needs small Firestore wiring
- T3 (client-local tools/MCPs) = client advertises at auth handshake → backend creates ephemeral proxy tools → routes tool calls back to client over WS

**Notifications + Cron:**
- `ScheduledTask` and `NotificationRule` are separate entities — a task *optionally* has a notify rule
- 3 execution modes: Cloud Tasks (one-off), Cloud Scheduler (recurring), direct call (agent-triggered)
- Agent tools: `schedule_task(action, schedule, notify_rule?)` + `send_notification(channel, message)` (immediate)
- Courier/Resend key stored per-user in Secret Manager — user manages their own credentials




































Fetched 2 resources

Good questions — both are worth designing carefully. Let me break each down.

---

## 1. Protocol-Ready, Client-Agnostic Backend

### Core Problem
Right now your backend partially does this already (`ClientType` enum, `ConnectionManager`), but it's **declaration-only** — the agent's tool set doesn't adapt to what the connected client can actually do.

### Proposed Approach: Capability Advertisement at Handshake

Extend the auth handshake so every client declares **what it is + what it can do**:

```json
{
  "type": "auth",
  "token": "...",
  "client_type": "desktop",
  "capabilities": ["write_file", "read_file", "capture_screen", "type_text", "run_command"]
}
```

**Key design decisions:**

| Layer | Approach |
|---|---|
| **Tool metadata** | Each tool declares `required_capabilities: set[str]` (e.g. `capture_screen` requires `["capture_screen"]`) |
| **ToolRegistry** | Central registry that returns filtered tool list based on `ConnectionManager.get_capabilities(user_id)` |
| **Agent tool set** | Rebuilt per session (or injected into system prompt) when active client capabilities change |
| **Capability change** | New `capability_update` WS message so mobile can grant camera after connect |

**Two valid implementation patterns:**

- **Hard gating** — `ToolRegistry.get_tools(user_id)` returns only tools whose capabilities exist in connected clients. Agent is built with those tools only, per session. Most correct — agent never hallucinates tools it can't use.
- **Soft gating** — All tools always registered, but `execute_*` tool functions check capability at runtime and return `{"error": "required client not connected"}`. Much simpler to implement. Agent can still describe what'd be possible.

**Soft gating** is the pragmatic first step; hard gating is the production target. This model means: add an ESP32 or new glasses client — no backend changes, it just advertises `["audio_capture", "display_text"]` and those tools become available.