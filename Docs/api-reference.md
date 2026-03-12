# API Reference

> Auto-generated REST API docs available at `http://localhost:8000/docs` (Swagger) when running the backend.

## REST Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Cloud Run healthcheck |
| POST | `/auth/verify` | Firebase token verification |
| GET/POST/PUT/DELETE | `/personas` | Persona CRUD |
| GET/DELETE | `/sessions` | Session history |
| GET/POST | `/mcp` | MCP plugin management (legacy wrapper) |
| GET/POST | `/plugins` | Unified plugin management (catalog, toggle, secrets, tools, OAuth) |
| POST | `/plugins/{id}/oauth/start` | Start OAuth flow for MCP_OAUTH plugin |
| GET | `/plugins/oauth/callback` | OAuth callback (handles token exchange) |
| POST | `/plugins/{id}/oauth/disconnect` | Revoke OAuth tokens and disconnect |
| GET | `/clients` | Connected device status |

## WebSocket Endpoints

| Path | Description |
|---|---|
| `/ws/live/{session_id}` | Bidirectional audio + text streaming (ADK) |
| `/ws/events/{session_id}` | Dashboard event stream (status, GenUI, tools) |

## WebSocket Message Schema

See `backend/app/models/ws_messages.py` for the full Pydantic schema definitions.

### Message Types (Client → Server)
- `auth` — Firebase ID token for session authentication
- `text` — Text message input
- `control` — Start/stop/interrupt session
- `image` — Image data (base64)

### Message Types (Server → Client)
- `response` — Agent text response
- `transcription` — Real-time speech transcript
- `status` — Agent state changes (listening, thinking, speaking, tool_use)
- `tool` — Tool invocation details
- `cross_client` — Cross-client action dispatch
- `error` — Error message
