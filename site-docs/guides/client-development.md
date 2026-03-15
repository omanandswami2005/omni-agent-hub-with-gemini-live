# Client Development

Guide for building new Omni clients that connect to the backend.

## Protocol Overview

All Omni clients communicate with the backend via **raw WebSocket** (not Socket.IO).

### Connection Flow

1. Connect to `wss://your-backend/ws/live/{session_id}`
2. Send an `auth` message with Firebase JWT token
3. Receive `auth_response` with user info and capabilities
4. Start sending/receiving audio (binary) and control (JSON) messages

### Auth Message

```json
{
  "type": "auth",
  "token": "firebase-jwt-token",
  "client_type": "desktop",
  "capabilities": ["screen_capture", "file_system", "execute_command"],
  "local_tools": [
    {
      "name": "capture_screen",
      "description": "Capture a screenshot",
      "parameters": { "type": "object", "properties": {} }
    }
  ]
}
```

### Message Types

| Direction | Type | Format | Description |
|---|---|---|---|
| Client → Server | Audio | Binary (PCM16) | 16kHz mono audio frames |
| Client → Server | Text | JSON `{type: "text", text: "..."}` | Text input |
| Server → Client | Audio | Binary (PCM24) | 24kHz audio response |
| Server → Client | Transcript | JSON | Agent text response |
| Server → Client | Tool invocation | JSON | T3 reverse-RPC call |
| Client → Server | Tool result | JSON | T3 tool execution result |

## T3 Tool Registration

Clients can advertise local tools that the AI agent can invoke remotely. See the [Desktop Client Architecture](../architecture/desktop-client.md) for a complete example.
