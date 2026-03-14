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

**Required handshake before streaming**: Send `mic_acquire` before your first audio frame. The server serialises all concurrent acquire requests so only one device streams at a time. Wait for `mic_floor:{event:"granted"}` before sending audio. When recording stops, send `mic_release`.

```json
// 1. Request the mic floor
{"type": "mic_acquire"}

// 2a. Server grants it
{"type": "mic_floor", "event": "granted", "holder": "mobile"}
// → safe to start sending binary PCM frames

// 2b. Server denies it (another device is already streaming)
{"type": "mic_floor", "event": "denied", "holder": "web"}
// → show the user that the mic is in use, don't start streaming

// 3. When recording stops, release explicit
{"type": "mic_release"}
```

All connected clients of the same user also receive a broadcast:

```json
{"type": "mic_floor", "event": "acquired", "holder": "mobile"}
// ... later ...
{"type": "mic_floor", "event": "released", "holder": "mobile"}
```

Use these broadcasts to update your UI (e.g. disable a "Start recording" button while another device holds the floor).

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
  "image_base64": "<base64>",   // present during live session (ephemeral)
  "image_url": "https://...",   // signed HTTPS URL (60-min TTL) — use for display/caching
  "mime_type": "image/png",
  "description": "A sunset over Tokyo"
}
```

For the rich multi-image tool (`generate_rich_image`) the payload uses `parts` instead:

```json
{
  "type": "image_response",
  "tool_name": "generate_rich_image",
  "parts": [
    {"type": "text", "content": "Step 1: ..."},
    {"type": "image", "image_url": "https://...", "mime_type": "image/png"},
    {"type": "text", "content": "Step 2: ..."},
    {"type": "image", "image_url": "https://...", "mime_type": "image/png"}
  ],
  "text": "Summary of the illustrated guide"
}
```

> **Image persistence**: `image_url` is a signed GCS URL valid for 60 minutes. Clients should use this URL for rendering rather than the `image_base64` field, which is only available during the live session and not stored. Sessions API (`GET /sessions/{id}/messages`) returns `image_url` / `parts[].image_url` for all historical messages so images survive page reloads.

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

### Mic floor events (multi-device — `/ws/live` only)

Broadcast to **all** connected clients of the user when the mic floor changes:

```json
// Another device started streaming
{"type": "mic_floor", "event": "acquired", "holder": "mobile"}

// That device stopped streaming
{"type": "mic_floor", "event": "released", "holder": "mobile"}

// Only sent to the requesting client — see "Send audio" section above
{"type": "mic_floor", "event": "granted", "holder": "web"}
{"type": "mic_floor", "event": "denied",  "holder": "mobile"}

// Fallback: server received raw audio before mic_acquire was sent (legacy clients)
{"type": "mic_floor", "event": "busy",    "holder": "desktop"}
```

### Cross-client rendering deduplication

When multiple clients are connected, events are fanned out via the EventBus to all of them. Each event carries `cross_client: true` when it originated on another device:

```json
{
  "type": "response",
  "data": "Here is the weather forecast...",
  "cross_client": true,
  "_origin_client_type": "mobile"
}
```

Clients on `/ws/live` receive only audio + their own messages. Clients on `/ws/chat` (or `/ws/events`) receive the cross-client text events. This split prevents the same text bubble from appearing twice on multi-socket setups.

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

## Reference Implementation — Smart Glasses (Audio + Video)

See `smart-glasses/glasses_client.py` for a complete `/ws/live` client with camera + microphone. Key patterns:

```python
import asyncio, json, base64, websockets, aiohttp, pyaudio

async def main(server, token, esp32_ip):
    async with aiohttp.ClientSession() as http:
        async with websockets.connect(f"{server}/ws/live") as ws:
            # 1. Auth handshake (register as "glasses" with T3 tools)
            await ws.send(json.dumps({
                "type": "auth",
                "token": token,
                "client_type": "glasses",
                "capabilities": ["camera_capture", "microphone", "speaker"],
                "local_tools": [{"name": "capture_photo", ...}],
            }))
            resp = json.loads(await ws.recv())
            assert resp["status"] == "ok"

            # 2. Acquire mic floor before streaming audio
            await ws.send(json.dumps({"type": "mic_acquire"}))

            # 3. Mic task — send PCM audio as binary frames
            async def send_audio():
                async for chunk in esp32_udp_audio_stream():
                    await ws.send(chunk)  # Binary frame → backend (16kHz PCM)

            # 4. Receiver — handle text JSON + binary audio
            async def receiver():
                async for msg in ws:
                    if isinstance(msg, bytes):
                        speaker_udp.sendto(msg, (ESP32_IP, SPEAKER_PORT))  # 24kHz PCM
                    else:
                        data = json.loads(msg)
                        if data.get("type") == "mic_floor" and data.get("event") == "granted":
                            pass  # Start flowing audio (mic_acquire was accepted)

            await asyncio.gather(send_audio(), receiver())
```

Hardware: ESP32-CAM + INMP441 I2S mic. See `smart-glasses/README.md` for wiring diagrams and firmware.

---

## Reference Implementation — ESP32 UDP Bridge (Python Host)

For setups where the ESP32 sends/receives raw **UDP** audio (instead of HTTP streaming), a Python host machine bridges UDP ↔ Omni Hub WebSocket:

```
ESP32 mic ──(UDP 4444)──► Python host ──(WSS /ws/live)──► Omni Hub backend
ESP32 spk ◄─(UDP 5555)── Python host ◄─(binary WS frames)─ Omni Hub backend
```

See `smart-glasses/esp32_udp_bridge.py` for the complete implementation. Key patterns:

```python
import asyncio, json, socket, websockets

UDP_MIC_PORT  = 4444   # Python listens — ESP32 sends PCM here
SPEAKER_IP    = "192.168.x.x"  # ESP32 IP
SPEAKER_PORT  = 5555   # Python sends PCM here — ESP32 plays it

async def main(token):
    # UDP listener (non-blocking via asyncio)
    loop = asyncio.get_event_loop()
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind(("0.0.0.0", UDP_MIC_PORT))
    udp_sock.setblocking(False)

    spk_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    async with websockets.connect("wss://omni-backend-fcapusldtq-uc.a.run.app/ws/live",
                                  max_size=2**20) as ws:
        # Auth
        await ws.send(json.dumps({"type": "auth", "token": token,
                                  "client_type": "glasses",
                                  "capabilities": ["microphone", "speaker"]}))
        auth_resp = json.loads(await ws.recv())
        assert auth_resp.get("status") == "ok"

        # Request mic floor
        await ws.send(json.dumps({"type": "mic_acquire"}))

        mic_granted = asyncio.Event()

        async def send_mic():
            await mic_granted.wait()   # don't send until server grants floor
            while True:
                data = await loop.sock_recv(udp_sock, 2048)
                await ws.send(data)    # raw PCM binary frame

        async def recv_speaker():
            async for msg in ws:
                if isinstance(msg, bytes):
                    # 24kHz PCM from backend → chunk and send to ESP32 speaker over UDP
                    chunk_size = 1024
                    for i in range(0, len(msg), chunk_size):
                        spk_sock.sendto(msg[i:i+chunk_size], (SPEAKER_IP, SPEAKER_PORT))
                        await asyncio.sleep(chunk_size / (16000 * 2))  # pace to real-time
                else:
                    data = json.loads(msg)
                    if data.get("type") == "mic_floor":
                        if data.get("event") == "granted":
                            mic_granted.set()
                        elif data.get("event") in ("denied", "busy"):
                            print("Mic in use by another device:", data.get("holder"))
                    elif data.get("type") == "mic_release":
                        mic_granted.clear()

        await asyncio.gather(send_mic(), recv_speaker())

asyncio.run(main(token="<firebase-jwt>"))
```

Audio format notes:
- **Input** (ESP32 → backend): 16kHz, 16-bit, mono, little-endian PCM, raw binary WS frames
- **Output** (backend → ESP32): 24kHz, 16-bit, mono, little-endian PCM, raw binary WS frames
- Pace UDP sends to match real-time playback (1024 bytes / (16000 Hz × 2 bytes) ≈ 32ms/chunk)

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
- [ ] For `/ws/live` audio: send `mic_acquire` before first PCM frame; wait for `granted`
- [ ] For `/ws/live` audio: send `mic_release` when recording stops
- [ ] Handle `mic_floor` broadcasts to disable/enable mic UI when another device is streaming
- [ ] Render images from `image_url` (not `image_base64`) to survive page reloads
- [ ] For `image_response` with `parts`: render text + image interleaved in order

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
