# Track 3: Client Developer Guide

> **Scope**: Build new clients (any language/platform) that connect to the Omni Hub backend.
> **Examples**: Desktop app, Chrome extension, mobile app, ESP32 glasses, VS Code extension, car dashboard
> **Prerequisites**: WebSocket library in your language, Firebase auth token
> **Protocol**: JSON text frames + optional binary PCM audio frames

---

## Architecture — One Backend, Any Surface

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Web Client  │   │   CLI Client  │   │  Glasses HW  │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │WS                │WS                │WS
       └──────────────────┼──────────────────┘
                          │
                ┌─────────▼─────────┐
                │   Omni Hub Backend │
                │   FastAPI + ADK    │
                │   port 8000        │
                └────────────────────┘
```

Every client connects to the **same backend, same agent**. The backend tracks which clients are online and routes messages/tool calls between them.

---

## Connection Flow

### Step 1: Open WebSocket

```
ws://localhost:8000/ws/chat    ← text only (recommended for non-audio clients)
ws://localhost:8000/ws/live    ← bidirectional audio + text
```

### Step 2: Auth Handshake

**Client sends first message** (JSON text frame):

```json
{
  "type": "auth",
  "token": "<firebase-id-token>",
  "client_type": "desktop",
  "capabilities": ["read_file", "write_file", "run_command"],
  "local_tools": [
    {
      "name": "read_file",
      "description": "Read a file from the user's desktop",
      "parameters": {
        "type": "object",
        "properties": {
          "path": { "type": "string", "description": "Absolute file path" }
        },
        "required": ["path"]
      }
    }
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"auth"` | Yes | Always `"auth"` |
| `token` | string | Yes | Firebase ID token (JWT) |
| `client_type` | string | Yes | One of: `web`, `desktop`, `chrome`, `mobile`, `glasses`, `cli`, `tv`, `car`, `iot`, `vscode`, `bot` |
| `capabilities` | string[] | No | What this client can do (advertised to agent) |
| `local_tools` | object[] | No | T3 tools — functions the agent can call ON this client (see T3 section below) |

**Server responds** (JSON text frame):

```json
{
  "type": "auth_response",
  "status": "ok",
  "user_id": "uid_abc123",
  "session_id": "ses_xyz",
  "firestore_session_id": "fs_789",
  "available_tools": ["search_wikipedia", "generate_image", "get_weather"],
  "other_clients_online": ["web", "glasses"]
}
```

If `status` is `"error"`, check the `error` field and close.

### Step 3: Send & Receive Messages

After successful auth, the client and server exchange messages in any order.

---

## Message Reference — Client → Server

### Send text

```json
{"type": "text", "content": "What's the weather in Tokyo?"}
```

### Send image (base64)

```json
{
  "type": "image",
  "data_base64": "<base64-encoded-image>",
  "mime_type": "image/jpeg"
}
```

### Switch persona

```json
{"type": "persona_switch", "persona_id": "teacher"}
```

### Toggle an MCP plugin

```json
{"type": "mcp_toggle", "mcp_id": "wikipedia", "enabled": true}
```

### Control actions

```json
{"type": "control", "action": "start_voice", "payload": null}
```

### Send audio (binary frames — `/ws/live` only)

Raw PCM audio: 16 kHz, 16-bit, mono, little-endian. Send as binary WebSocket frames.

---

## Message Reference — Server → Client

### Agent text/genui response

```json
{
  "type": "response",
  "content_type": "text",    // "text" | "audio" | "genui" | "transcription"
  "data": "The weather in Tokyo is 22°C and sunny.",
  "genui": null              // populated when content_type == "genui"
}
```

### Transcription (speech-to-text / text-to-speech)

```json
{
  "type": "transcription",
  "direction": "input",     // "input" = user spoke, "output" = agent spoke
  "text": "What's the weather in Tokyo?",
  "finished": true
}
```

### Tool call started/completed

```json
{
  "type": "tool_call",
  "tool_name": "get_weather",
  "arguments": {"city": "Tokyo"},
  "status": "started"        // "started" | "completed" | "failed"
}
```

### Tool result

```json
{
  "type": "tool_response",
  "tool_name": "get_weather",
  "result": "{\"temp_c\": \"22\", \"condition\": \"Sunny\"}",
  "success": true
}
```

### Image response

```json
{
  "type": "image_response",
  "tool_name": "generate_image",
  "image_base64": "<base64>",
  "mime_type": "image/png",
  "description": "A sunset over Tokyo"
}
```

### Agent activity (sub-agent calls, reasoning, etc.)

```json
{
  "type": "agent_activity",
  "activity_type": "tool_call",    // "sub_agent_call" | "reasoning" | "mcp_call" | "tool_call" | "waiting"
  "title": "Searching Wikipedia",
  "details": "Querying for 'Tokyo weather'",
  "status": "started",             // "started" | "in_progress" | "completed" | "failed"
  "progress": 0.5,
  "parent_agent": "root"
}
```

### Status updates

```json
{"type": "status", "state": "processing", "detail": ""}
```

States: `idle`, `listening`, `processing`, `speaking`, `error`

### Errors

```json
{"type": "error", "code": "rate_limit", "description": "Too many requests"}
```

### Persona changed

```json
{
  "type": "persona_changed",
  "persona_id": "teacher",
  "persona_name": "Teacher",
  "voice": "Kore"
}
```

### Cross-client action

```json
{
  "type": "cross_client",
  "action": "open_url",
  "target": "desktop",
  "data": {"url": "https://example.com"}
}
```

### Session suggestion (multi-device)

```json
{
  "type": "session_suggestion",
  "available_clients": ["desktop", "mobile"],
  "message": "Continue this session on your desktop?"
}
```

---

## T3 Tools — Reverse-RPC (Agent Calls YOUR Client)

T3 is the most powerful integration pattern: the agent can call tools that **run on the client device**. For example, a desktop client can expose `read_file`, `run_command`, `open_app`.

### How it works

1. Client advertises `local_tools` in the auth message
2. Backend creates T3 proxy tools (agent sees them like any other tool)
3. When the agent wants to call a T3 tool, the backend sends a `tool_invocation` to the client
4. The client executes the tool locally and sends a `tool_result` back

### Server → Client: tool_invocation

```json
{
  "type": "tool_invocation",
  "call_id": "uuid-123",
  "tool": "read_file",
  "args": {"path": "/home/user/notes.txt"}
}
```

### Client → Server: tool_result

```json
{
  "type": "tool_result",
  "call_id": "uuid-123",
  "result": {"status": "ok", "content": "Hello world!"}
}
```

**Important**: The `call_id` must match. The backend waits up to **30 seconds** for the result. If you don't respond in time, the tool call fails.

### Defining local tools

```json
{
  "local_tools": [
    {
      "name": "read_file",
      "description": "Read a file from the user's filesystem",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {"type": "string", "description": "Absolute path to the file"}
        },
        "required": ["path"]
      }
    },
    {
      "name": "run_command",
      "description": "Execute a shell command on the user's machine",
      "parameters": {
        "type": "object",
        "properties": {
          "command": {"type": "string", "description": "Shell command to run"}
        },
        "required": ["command"]
      }
    }
  ]
}
```

---

## Reference Implementation — CLI Client

See `cli/omni_cli.py` for a complete working client (~185 lines of Python). Key patterns:

```python
import asyncio, json, websockets

async def main(server, token, capabilities, local_tools):
    async with websockets.connect(f"{server}/ws/chat") as ws:
        # 1. Auth handshake
        await ws.send(json.dumps({
            "type": "auth",
            "token": token,
            "client_type": "cli",
            "capabilities": capabilities,
            "local_tools": local_tools,
        }))
        resp = json.loads(await ws.recv())
        assert resp["status"] == "ok"

        # 2. Reader task (prints server messages)
        async def reader():
            async for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "response":
                    print(f"Agent: {msg['data']}")
                elif msg["type"] == "tool_invocation":
                    # T3 reverse-RPC
                    result = execute_local_tool(msg["tool"], msg["args"])
                    await ws.send(json.dumps({
                        "type": "tool_result",
                        "call_id": msg["call_id"],
                        "result": result,
                    }))

        reader_task = asyncio.create_task(reader())

        # 3. Send user messages
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, input)
            await ws.send(json.dumps({"type": "text", "content": line}))
```

---

## Client Types

Register your client as one of these types:

| Type | Example |
|------|---------|
| `web` | React dashboard |
| `desktop` | Electron / Tauri app |
| `chrome` | Chrome extension |
| `mobile` | React Native / Flutter |
| `glasses` | ESP32 smart glasses |
| `cli` | Terminal REPL |
| `tv` | Smart TV app |
| `car` | Car infotainment |
| `iot` | IoT device |
| `vscode` | VS Code extension |
| `bot` | Automated bot/agent |

---

## REST API Endpoints

Some operations use REST instead of WebSocket:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/verify` | POST | Verify Firebase token |
| `/api/v1/init/bootstrap` | POST | Create agent session and get config |
| `/api/v1/personas/list` | GET | List available personas |
| `/api/v1/plugins/catalog` | GET | List available plugins |
| `/api/v1/plugins/toggle` | POST | Enable/disable a plugin |
| `/api/v1/clients/online` | GET | Get online client list |
| `/api/v1/sessions/{id}` | GET | Get session details |
| `/api/v1/mcp/*` | Various | MCP management |

---

## Implementation Checklist

- [ ] Connect to `ws://host:8000/ws/chat` (or `/ws/live` for audio)
- [ ] Send auth message with your `client_type`
- [ ] Handle `auth_response` — check `status == "ok"`
- [ ] Handle `response` messages (agent text output)
- [ ] Handle `status` messages (show loading states)
- [ ] Handle `error` messages (show error to user)
- [ ] Handle `tool_call`/`tool_response` (optional — show tool activity)
- [ ] Handle `transcription` (optional — show speech transcripts)
- [ ] Handle `image_response` (optional — display generated images)
- [ ] Handle `agent_activity` (optional — show reasoning/progress)
- [ ] Handle `cross_client` (optional — act on cross-device commands)
- [ ] Implement T3 `tool_invocation` → `tool_result` (optional — if advertising local tools)
- [ ] Handle connection drops with reconnect logic

---

## FAQ

**Q: What auth token do I need?**
A: A Firebase ID token (JWT). Get it from `firebase.auth().currentUser.getIdToken()` in web, or the Firebase SDK in your platform.

**Q: Can I connect multiple clients for the same user?**
A: Yes — the backend tracks all connected clients per user. They share the same agent session.

**Q: What happens if my client disconnects?**
A: The backend removes it from the online list. Reconnect and re-auth to resume.

**Q: Do I need to handle all message types?**
A: No. At minimum handle `auth_response`, `response`, `status`, and `error`. Other types are optional enhancements.

**Q: What encoding for binary audio frames?**
A: PCM 16-bit little-endian, mono, 16kHz sample rate for input. Server sends 24kHz for output.
