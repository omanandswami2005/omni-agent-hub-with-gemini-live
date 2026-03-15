# WebSocket API Reference

## Connection

```
wss://your-backend/ws/live/{session_id}
```

The `session_id` can be `new` for a fresh session or an existing session ID to resume.

## Authentication

First message must be an `auth` message:

```json
{
  "type": "auth",
  "token": "firebase-jwt-token",
  "client_type": "web | desktop | chrome_extension | cli | glasses",
  "capabilities": ["screen_capture", "file_system"],
  "local_tools": []
}
```

## Message Types

### Client → Server

| Type | Format | Description |
|---|---|---|
| `auth` | JSON | Authentication (first message) |
| Audio | Binary | PCM16 16kHz mono audio frames |
| `text` | JSON `{type: "text", text: "..."}` | Text input |
| `control` | JSON `{type: "control", action: "..."}` | Control commands |
| `tool_result` | JSON | T3 tool execution result |
| `interrupt` | JSON `{type: "interrupt"}` | Interrupt current response |

### Server → Client

| Type | Format | Description |
|---|---|---|
| `auth_response` | JSON | Auth result + user info |
| Audio | Binary | PCM16 24kHz mono response audio |
| `transcript` | JSON | Agent text response |
| `agent_response` | JSON | Full agent response with GenUI |
| `tool_invocation` | JSON | T3 reverse-RPC call |
| `tool_list` | JSON | Available tools for the session |
| `session_suggestion` | JSON | Suggested session to resume |
| `client_status_update` | JSON | Connected device changes |
| `status` | JSON | Agent status (thinking, speaking) |
| `cancel` | JSON | Cancel pending tool invocations |
