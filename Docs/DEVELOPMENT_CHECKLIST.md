# OMNI — Development Checklist (Feature-by-Feature)

> **Project**: Omni — Speak anywhere. Act everywhere.
> **Category**: Live Agents — Real-time Interaction (Audio/Vision)
> **Deadline**: March 17, 2026
> **Hackathon**: Gemini Live Agent Challenge ($80K prizes)

---

## Agent Prompt (Paste This to Your Code Agent)

```
You are implementing features for "Omni" — a multi-client, single-server AI agent hub for the Gemini Live Agent Challenge hackathon.

BEFORE starting any task from DEVELOPMENT_CHECKLIST.md:
1. Read the task description and acceptance criteria carefully.
2. Read the referenced sections from RESEARCH_AND_PLAN.md for deep technical context (section numbers are provided).
3. Read PROJECT_STRUCTURE_AND_UI_SPECS.md for folder structure, UI specs, and API contracts.
4. Read GCP_AND_VERTEX_AI_FEATURES.md for Vertex AI integration details.
5. Verify your implementation fits the existing scalable folder structure — never create files outside the established structure.
6. Verify Vertex AI / Google Cloud integration is correct (correct SDK usage, correct model names, correct API patterns).
7. Implement the feature with production-quality code.
8. Write at least ONE test per task (unit test or integration test) in the corresponding tests/ directory.
9. Run linting (ruff for Python, ESLint for JS) and fix any issues before marking complete.

KEY TECHNICAL CONSTRAINTS:
- Transport: Raw WebSocket (NOT Socket.IO). Binary frames for audio, JSON for control messages.
- Backend: Python 3.12+, FastAPI, google-adk >= 0.5.0, websockets, uv package manager.
- Frontend: React 19 (JavaScript, NOT TypeScript), Vite 6, Tailwind CSS 4, shadcn/ui, Zustand 5.
- Audio: 16-bit PCM — 16kHz input (mic), 24kHz output (playback). AudioWorklet (NOT ScriptProcessor).
- Models: gemini-live-2.5-flash-native-audio (Vertex AI) for live audio, gemini-2.5-flash for text tasks.
- Agent Framework: Google ADK — LlmAgent, SequentialAgent, ParallelAgent, LoopAgent, CustomAgent.
- MCP: McpToolset with StreamableHTTPConnectionParams (remote) and StdioConnectionParams (local).
- Sandboxing: E2B primary, Agent Engine Code Execution as fallback.
- Auth: Firebase Auth (Google sign-in), JWT validation on every request + WS upgrade.
- Database: Firestore (sessions, personas, MCP configs, client registry).
- State: Zustand stores (8 stores: auth, chat, persona, mcp, client, session, theme, ui).
- Linting: Ruff (Python), ESLint 9 flat config (JS), Prettier with Tailwind plugin.

FOLDER STRUCTURE RULES:
- Backend code: backend/app/{api,agents,tools,services,middleware,models,utils}/
- Backend tests: backend/tests/{test_api,test_agents,test_services,test_tools}/
- Frontend components: dashboard/src/components/{layout,chat,genui,persona,mcp,clients,session,sandbox,auth,shared,ui}/
- Frontend pages: dashboard/src/pages/
- Frontend stores: dashboard/src/stores/
- Frontend hooks: dashboard/src/hooks/
- Frontend utils: dashboard/src/lib/
- Desktop client: desktop-client/src/
- Chrome extension: chrome-extension/
- Deploy/infra: deploy/{terraform,scripts}/

After implementing, verify:
✅ Code follows existing patterns in the codebase
✅ No new files outside established folder structure
✅ Vertex AI / GCP integration uses correct SDKs and patterns
✅ At least one test written and passing
✅ Linting passes (ruff check backend/, pnpm run lint in dashboard/)
```

---

## How to Use This Checklist

- Tasks are ordered **sequentially** — start from Task 1 and proceed in order.
- Each task has **dependencies** listed — do not skip ahead unless deps are met.
- **Research Refs** point to exact sections in `RESEARCH_AND_PLAN.md` (R&P), `PROJECT_STRUCTURE_AND_UI_SPECS.md` (PS), and `GCP_AND_VERTEX_AI_FEATURES.md` (GCP).
- Each task targets specific **files** in the established folder structure.
- Mark `[x]` when complete.

---

## Phase 1: Backend Core Foundation (Tasks 1–8)

### Task 1: FastAPI Application Bootstrap & Config

- [ ] **1.1** — Implement `backend/app/config.py` with Pydantic Settings loading all env vars (GCP project, location, Firebase, E2B, CORS origins, environment)
- [ ] **1.2** — Implement `backend/app/main.py` with FastAPI app factory, lifespan context manager (startup/shutdown), CORS middleware, and router includes
- [ ] **1.3** — Implement `backend/app/middleware/cors.py` with configurable CORS origins from config
- [ ] **1.4** — Implement `backend/app/api/health.py` with `GET /health` returning status, version, and uptime
- [ ] **1.5** — Implement `backend/app/api/router.py` to include all API sub-routers under `/api/v1`
- [ ] **1.6** — Implement `backend/app/utils/logging.py` with structlog configuration (JSON output, request_id binding, Cloud Logging integration)
- [ ] **1.7** — Implement `backend/app/utils/errors.py` with exception hierarchy (AppError, AuthError, NotFoundError, ValidationError) and FastAPI exception handlers
- [ ] **1.8** — Write test: `backend/tests/test_api/test_health.py` — verify `/health` returns 200 with correct schema

**Dependencies**: None (first task)
**Files**: `backend/app/config.py`, `backend/app/main.py`, `backend/app/middleware/cors.py`, `backend/app/api/health.py`, `backend/app/api/router.py`, `backend/app/utils/logging.py`, `backend/app/utils/errors.py`, `backend/tests/test_api/test_health.py`
**Research Refs**: R&P Section 9 (Architecture), PS Section 1 (Folder Structure), PS Section 12 (Developer Workflow)
**Verify**: `uv run python -m uvicorn app.main:app --port 8000` starts successfully, `/health` responds, structlog outputs JSON

---

### Task 2: Firebase Auth Middleware & Auth API

- [ ] **2.1** — Implement `backend/app/middleware/auth_middleware.py` with Firebase JWT verification using `firebase-admin` SDK, extracting `user_id` from token and injecting into request state
- [ ] **2.2** — Implement `backend/app/api/auth.py` with `POST /api/v1/auth/verify` (validate token, return user profile), `GET /api/v1/auth/me` (current user info)
- [ ] **2.3** — Add auth dependency function that can be injected into FastAPI route handlers (`Depends(get_current_user)`)
- [ ] **2.4** — Handle token expiry gracefully — return 401 with clear error message for WebSocket reconnection
- [ ] **2.5** — Write test: `backend/tests/test_api/test_auth.py` — test valid token, expired token, missing token scenarios (mock Firebase Admin)

**Dependencies**: Task 1
**Files**: `backend/app/middleware/auth_middleware.py`, `backend/app/api/auth.py`, `backend/tests/test_api/test_auth.py`
**Research Refs**: R&P Section 9 (Architecture), PS Section 8 (API Layer & Security), GCP Section on Firebase Auth
**Verify**: Protected endpoints return 401 without token, 200 with valid token

---

### Task 3: Firestore Integration & Session Service

- [ ] **3.1** — Implement `backend/app/services/session_service.py` with Firestore-backed session CRUD: `create_session()`, `get_session()`, `update_session()`, `delete_session()`, `list_sessions(user_id)`
- [ ] **3.2** — Implement `backend/app/models/session.py` with Pydantic models: `SessionCreate`, `SessionUpdate`, `SessionResponse`, `SessionListItem`
- [ ] **3.3** — Implement `backend/app/api/sessions.py` with REST endpoints: `POST /sessions`, `GET /sessions`, `GET /sessions/{id}`, `DELETE /sessions/{id}` (all user-scoped via auth)
- [ ] **3.4** — Ensure Firestore collections are indexed on `user_id` + `created_at` for efficient queries
- [ ] **3.5** — Write test: `backend/tests/test_services/test_session_service.py` — test CRUD operations with mocked Firestore client

**Dependencies**: Task 1, Task 2
**Files**: `backend/app/services/session_service.py`, `backend/app/models/session.py`, `backend/app/api/sessions.py`, `backend/tests/test_services/test_session_service.py`
**Research Refs**: R&P Section 9 (Architecture), PS Section 8 (API Layer), GCP Section 4.2 (Agent Engine Sessions)
**Verify**: Sessions persist across server restarts, user can only access their own sessions

---

### Task 4: Pydantic Models & WebSocket Message Protocol

- [ ] **4.1** — Implement `backend/app/models/ws_messages.py` with all WebSocket message types as Pydantic models:
  - `AuthMessage` (type: "auth", token)
  - `AuthResponse` (type: "auth_response", status, user_id, session_id)
  - `TextMessage` (type: "text", content)
  - `ImageMessage` (type: "image", data_base64, mime_type)
  - `PersonaSwitchMessage` (type: "persona_switch", persona_id)
  - `MCPToggleMessage` (type: "mcp_toggle", mcp_id, enabled)
  - `AgentResponse` (type: "response", content_type, data — supports text/audio/genui/transcription)
  - `ToolCallMessage` (type: "tool_call", tool_name, arguments, status)
  - `ToolResponseMessage` (type: "tool_response", tool_name, result)
  - `ErrorMessage` (type: "error", code, description)
  - `StatusMessage` (type: "status", state — connected/thinking/speaking/idle)
  - `WSMessage` discriminated union of all types
- [ ] **4.2** — Implement `backend/app/models/client.py` with `ClientInfo`, `ClientType` (web, desktop, chrome, mobile, glasses), `ClientStatus`
- [ ] **4.3** — Implement `backend/app/models/persona.py` with `PersonaCreate`, `PersonaUpdate`, `PersonaResponse` — fields: name, voice, system_instruction, mcp_ids, avatar_url, **capabilities** (list of `ToolCapability` tags)
- [ ] **4.4** — Implement `backend/app/models/mcp.py` with `MCPConfig`, `MCPCatalogItem`, `MCPCategory`
- [ ] **4.5** — Write test: `backend/tests/test_api/test_ws_messages.py` — test serialization/deserialization of each message type, discriminated union parsing

**Dependencies**: Task 1
**Files**: `backend/app/models/ws_messages.py`, `backend/app/models/client.py`, `backend/app/models/persona.py`, `backend/app/models/mcp.py`, `backend/tests/test_api/test_ws_messages.py`
**Research Refs**: PS Section 9 (WebSocket Protocol), PS Section 10 (State Management)
**Verify**: All message types round-trip correctly through JSON serialization

---

### Task 5: WebSocket Connection Manager & Client Registry

- [ ] **5.1** — Implement `backend/app/services/connection_manager.py` with:
  - `ConnectionManager` class: stores active WebSocket connections per user per client_type
  - `connect(websocket, user_id, client_type)` — register connection
  - `disconnect(websocket, user_id, client_type)` — cleanup connection
  - `send_to_user(user_id, message)` — broadcast to all user's clients
  - `send_to_client(user_id, client_type, message)` — target specific client
  - `get_connected_clients(user_id)` — list active clients for a user
- [ ] **5.2** — Implement `backend/app/services/client_registry.py` as import alias / re-export from connection_manager for backward compatibility
- [ ] **5.3** — Implement `backend/app/api/clients.py` with `GET /api/v1/clients` (list connected clients for auth'd user)
- [ ] **5.4** — Handle WebSocket disconnect gracefully — cleanup connection state, update Firestore client status
- [ ] **5.5** — Write test: `backend/tests/test_services/test_connection_manager.py` — test connect/disconnect/broadcast with mock WebSocket objects

**Dependencies**: Task 1, Task 4
**Files**: `backend/app/services/connection_manager.py`, `backend/app/services/client_registry.py`, `backend/app/api/clients.py`, `backend/tests/test_services/test_connection_manager.py`
**Research Refs**: R&P Section 9 (Architecture — Client Registry), PS Section 1 (Folder Structure), R&P Transport Decision (Raw WebSocket)
**Verify**: Multiple clients can connect simultaneously, messages route to correct client_type

---

### Task 6: ADK Root Agent & Persona System (3-Layer Architecture)

- [ ] **6.1** — Implement `backend/app/agents/root_agent.py` — `build_root_agent(personas, tools_by_persona, model, mcp_tools)` with 3-layer routing:
  - Layer 1: Persona Pool — each persona gets capability-matched T1+T2 tools
  - Layer 2: `plan_task` FunctionTool — delegates to TaskArchitect for complex multi-step requests
  - Layer 3: `device_agent` — cross-client orchestration with T3 proxy tools
  - Dynamic instruction listing all available personas and their capabilities
- [ ] **6.2** — Implement `backend/app/agents/personas.py` with 5 DEFAULT_PERSONAS (each with `capabilities` list):
  - **assistant**: capabilities=[search, web, knowledge, communication, media]. Voice: `Puck`
  - **coder**: capabilities=[code_execution, sandbox, search, web]. Voice: `Kore`
  - **researcher**: capabilities=[search, web, knowledge]. Voice: `Aoede`
  - **analyst**: capabilities=[code_execution, sandbox, search, data, web]. Voice: `Charon`
  - **creative**: capabilities=[creative, media]. Voice: `Leda`
- [ ] **6.3** — Implement `backend/app/agents/agent_factory.py` with:
  - `ToolCapability(StrEnum)` enum (11 tags) + `T1_TOOL_REGISTRY` mapping capabilities to tool factories
  - `get_tools_for_capabilities(caps)` — returns only the T1 tools matching a persona's declared capabilities
  - `build_persona_agent(persona, tools)` — builds an ADK `LlmAgent` with matched tools
- [ ] **6.3b** — Implement `backend/app/agents/cross_client_agent.py` — `build_cross_client_agent(device_tools, model)` returns `device_agent`
- [ ] **6.3c** — Implement `backend/app/agents/task_planner_tool.py` — `get_task_planner_tool()` returns `plan_task FunctionTool` wrapping TaskArchitect
- [ ] **6.4** — Implement `backend/app/services/tool_registry.py` — `build_for_session(user_id, personas)` returns `dict[str, list]` (per-persona tools + `__device__` key) using capability matching
- [ ] **6.5** — Implement `backend/app/services/persona_service.py` with Firestore-backed persona CRUD: `list_personas(user_id)`, `create_persona()`, `update_persona()`, `delete_persona()`, `get_default_personas()`
- [ ] **6.6** — Implement `backend/app/api/personas.py` with REST endpoints: `GET /personas`, `POST /personas`, `PUT /personas/{id}`, `DELETE /personas/{id}`
- [ ] **6.7** — Write test: `backend/tests/test_agents/test_root_agent.py` — test that root agent builds with persona AgentTools (6 personas as tools) and utility tools (plan_task, cross-client, capabilities)

**Dependencies**: Task 1, Task 2, Task 3
**Files**: `backend/app/agents/root_agent.py`, `backend/app/agents/personas.py`, `backend/app/agents/agent_factory.py`, `backend/app/agents/cross_client_agent.py`, `backend/app/agents/task_planner_tool.py`, `backend/app/services/tool_registry.py`, `backend/app/services/persona_service.py`, `backend/app/api/personas.py`, `backend/tests/test_agents/test_root_agent.py`
**Research Refs**: R&P Section 2 (ADK Agent Types), R&P Section 3 (Voice Config — 8 voices), R&P Section 9 (Multi-Agent Architecture), GCP Tier 1 (ADK)
**Verify**: Root agent correctly builds with AgentTool pattern — persona AgentTools with capability-matched tools, plan_task tool, and cross-client tools on root directly

---

### Task 7: Gemini Live API WebSocket Endpoint (Core Audio Pipeline)

- [ ] **7.1** — Implement `backend/app/api/ws_live.py` with the core bidirectional WebSocket endpoint `ws://host/ws/live`:
  - Accept WebSocket connection
  - First message: authenticate (parse `AuthMessage`, validate Firebase JWT)
  - On auth success: send `AuthResponse`, create/resume ADK session
  - Upstream task: receive binary audio frames (PCM16 16kHz) + JSON control messages from client, push to `LiveRequestQueue`
  - Downstream task: receive agent responses from ADK `run_live()`, send binary audio (PCM16 24kHz) + JSON (text/genui/status) to client
  - Use `asyncio.gather(upstream, downstream)` for bidirectional streaming
  - Handle barge-in: when new user audio arrives during agent speech, cancel current response
  - Handle disconnection gracefully
- [ ] **7.2** — Configure ADK `RunConfig` with:
  - `speech_config` for voice selection per persona
  - `response_modalities: ["AUDIO"]` for native audio output
  - `session_resumption` for reconnection support
- [ ] **7.3** — Implement verbal acknowledgments: when agent starts tool call, send spoken "Let me check on that..." before the tool executes
- [ ] **7.4** — Write test: `backend/tests/test_api/test_ws_live.py` — test WebSocket connection lifecycle (connect → auth → message → disconnect) with mock ADK runner

**Dependencies**: Task 1, Task 2, Task 4, Task 5, Task 6
**Files**: `backend/app/api/ws_live.py`, `backend/tests/test_api/test_ws_live.py`
**Research Refs**: R&P Section 3 (Gemini Live API — full audio specs, FastAPI pattern, upstream/downstream), R&P Section 3.2 (SDK patterns), GCP Section 4.10 (Gemini Live API deep dive)
**Verify**: Can establish WebSocket connection, send audio, receive audio response with correct sample rates

---

### Task 8: Dashboard WebSocket Event Channel

- [ ] **8.1** — Implement `backend/app/api/ws_events.py` with a secondary WebSocket endpoint `ws://host/ws/events` for dashboard-specific real-time updates:
  - Client status changes (device connected/disconnected)
  - Tool call progress (tool_name, status: started/completed/failed)
  - Session metadata updates
  - GenUI component delivery (chart/table/card data)
  - Agent status transitions (idle → thinking → speaking → idle)
- [ ] **8.2** — Connect event channel to ConnectionManager — events are broadcast to all user's dashboard clients
- [ ] **8.3** — Write test: `backend/tests/test_api/test_ws_events.py` — test event broadcasting to multiple connected dashboards

**Dependencies**: Task 5, Task 7
**Files**: `backend/app/api/ws_events.py`, `backend/tests/test_api/test_ws_events.py`
**Research Refs**: PS Section 9 (WebSocket Protocol — Message Types), R&P Section 9 (Architecture)
**Verify**: Dashboard receives real-time updates without polling

---

## Phase 2: Backend Tools & Integrations (Tasks 9–14)

### Task 9: Google Search Grounding Tool

- [ ] **9.1** — Implement `backend/app/tools/search.py` with ADK tool wrapping Google Search grounding:
  - `google_search(query)` — performs grounded search via Vertex AI
  - Returns results with inline citations
  - Anti-hallucination: all factual claims backed by search results
- [ ] **9.2** — Register as default tool for Researcher (Sage) and Assistant (Claire) personas
- [ ] **9.3** — Write test: `backend/tests/test_tools/test_search.py` — test search tool returns results with citation format

**Dependencies**: Task 6
**Files**: `backend/app/tools/search.py`, `backend/tests/test_tools/test_search.py`
**Research Refs**: R&P Section 9 (Architecture — Google Search Grounding), GCP Tier 1 (Grounding with Google Search)
**Verify**: Search results include citations, agent answers are fact-checked

---

### Task 10: E2B Code Execution Service

- [ ] **10.1** — Implement `backend/app/services/e2b_service.py` with:
  - `E2BService` class: manage sandbox lifecycle
  - `create_sandbox()` — spin up E2B sandbox (< 200ms cold start)
  - `execute_code(code, language)` — run Python/JS in sandbox, return stdout/stderr/result
  - `execute_command(command)` — run shell commands in sandbox
  - `upload_file(path, content)` / `download_file(path)` — file I/O in sandbox
  - `destroy_sandbox()` — cleanup
  - Timeout handling (max 60s per execution)
  - Error recovery with clear error messages
- [ ] **10.2** — Implement `backend/app/tools/code_exec.py` as ADK tool:
  - `execute_code(code, language="python")` — exposed to agents
  - `install_package(package_name)` — install pip/pnpm packages in sandbox
  - Returns structured result: `{stdout, stderr, exit_code, files_created}`
- [ ] **10.3** — Register as default tool for Coder (Dev) and Analyst (Nova) personas
- [ ] **10.4** — Write test: `backend/tests/test_tools/test_code_exec.py` — test code execution with mock E2B client (success, error, timeout scenarios)

**Dependencies**: Task 6
**Files**: `backend/app/services/e2b_service.py`, `backend/app/tools/code_exec.py`, `backend/tests/test_tools/test_code_exec.py`
**Research Refs**: R&P Section 4 (E2B Sandbox Research — API, MCP Gateway, pricing), GCP Section 4.4 (Code Execution fallback)
**Verify**: Code executes in isolated sandbox, errors are caught, files can be read/written

---

### Task 11: MCP Manager & Dynamic Tool Loading

- [ ] **11.1** — Implement `backend/app/services/mcp_manager.py` with:
  - `MCPManager` class: manages all MCP connections for a user session
  - `load_user_mcps(user_id)` — read enabled MCPs from Firestore, connect to each
  - `connect_mcp(mcp_config)` — establish connection via `McpToolset` with `StreamableHTTPConnectionParams` (remote) or `StdioConnectionParams` (local)
  - `disconnect_mcp(mcp_id)` — tear down connection
  - `get_tools()` — return all active MCP tools for injection into agent
  - `toggle_mcp(mcp_id, enabled)` — enable/disable at runtime (mid-conversation)
  - Cleanup on session end: close all MCP connections
- [ ] **11.2** — Implement `backend/app/api/mcp.py` with REST endpoints:
  - `GET /api/v1/mcp/catalog` — list available MCPs with categories
  - `GET /api/v1/mcp/enabled` — list user's enabled MCPs
  - `POST /api/v1/mcp/toggle` — enable/disable an MCP
  - `GET /api/v1/mcp/{id}` — MCP detail (description, auth requirements, tools list)
- [ ] **11.3** — Implement MCP catalog seed data: pre-configured entries for Brave Search, Playwright, GitHub, Notion, Google Calendar, Slack, Wolfram Alpha, Wikipedia, Filesystem
- [ ] **11.4** — Write test: `backend/tests/test_services/test_mcp_manager.py` — test MCP loading, tool injection, toggle, cleanup

**Dependencies**: Task 1, Task 2, Task 6
**Files**: `backend/app/services/mcp_manager.py`, `backend/app/api/mcp.py`, `backend/tests/test_services/test_mcp_manager.py`
**Research Refs**: R&P Section 5 (MCP Ecosystem — connection types, architecture), R&P Section 7 (Trending MCPs), R&P Section 4 (E2B MCP Gateway)
**Verify**: MCPs load dynamically, tools appear in agent's toolset, toggle works mid-session

---

### Task 12: Cross-Client Action Tools

- [ ] **12.1** — Implement `backend/app/tools/cross_client.py` with ADK tools for cross-client orchestration:
  - `send_to_desktop(action, params)` — trigger desktop client action (open app, type text, click, screenshot)
  - `send_to_chrome(action, params)` — trigger chrome extension action (open tab, click element, read page)
  - `send_to_dashboard(genui_component)` — push GenUI data to dashboard
  - `capture_screen(client_type)` — request screenshot from desktop or chrome
  - `notify_client(client_type, message)` — send notification to specific client
- [ ] **12.2** — Wire tools through ConnectionManager — each tool sends WebSocket message to target client_type and waits for `tool_response`
- [ ] **12.3** — Implement timeout + fallback: if target client not connected, return helpful error to agent
- [ ] **12.4** — Write test: `backend/tests/test_tools/test_cross_client.py` — test tool routing with mock ConnectionManager

**Dependencies**: Task 5, Task 7
**Files**: `backend/app/tools/cross_client.py`, `backend/tests/test_tools/test_cross_client.py`
**Research Refs**: R&P Section 8 (Desktop Client — ADK Tools), R&P Section 9 (Architecture — Cross-Client Killer Feature)
**Verify**: Agent can trigger action on desktop client, receive response, and relay to user

---

### Task 13: Image Generation Tool (Imagen 4)

- [ ] **13.1** — Implement `backend/app/tools/image_gen.py` with ADK tool:
  - `generate_image(prompt, style=None, aspect_ratio="1:1")` — calls Imagen 4 via Vertex AI
  - Returns image as base64 + pushes to dashboard as GenUI `image_gallery` component
  - Stores generated images in Cloud Storage (GCS)
  - Returns GCS URL for persistence
- [ ] **13.2** — Register as default tool for Creative (Muse) persona, available as optional for others
- [ ] **13.3** — Write test: `backend/tests/test_tools/test_image_gen.py` — test image generation with mock Vertex AI client

**Dependencies**: Task 6, Task 8
**Files**: `backend/app/tools/image_gen.py`, `backend/tests/test_tools/test_image_gen.py`
**Research Refs**: GCP Section 4.9 (Imagen 4 — 2K text-to-image), R&P Section 9 (GenUI — image_gallery component)
**Verify**: Image generates, stores in GCS, appears in dashboard GenUI panel

---

### Task 14: RAG Engine & Storage Service

- [ ] **14.1** — Implement `backend/app/tools/rag.py` with ADK tool:
  - `search_documents(query)` — semantic search across user's uploaded documents via Vertex AI RAG Engine
  - `upload_document(file_bytes, filename)` — ingest document into RAG corpus
  - Returns relevant chunks with source attribution
- [ ] **14.2** — Implement `backend/app/services/storage_service.py` with Cloud Storage operations:
  - `upload_file(bucket, path, content)` — upload to GCS
  - `download_file(bucket, path)` — retrieve from GCS
  - `generate_signed_url(bucket, path, expiry)` — temporary access URL
  - `list_files(bucket, prefix)` — list user files
- [ ] **14.3** — Write test: `backend/tests/test_services/test_storage_service.py` — test GCS operations with mock client

**Dependencies**: Task 1, Task 6
**Files**: `backend/app/tools/rag.py`, `backend/app/services/storage_service.py`, `backend/tests/test_services/test_storage_service.py`
**Research Refs**: GCP Section 4.6-4.8 (Grounding — RAG Engine), R&P Section 9 (Architecture)
**Verify**: Documents upload to GCS, RAG search returns relevant chunks with sources

---

## Phase 3: Backend Advanced Features (Tasks 15–18)

### Task 15: TaskArchitect — Dynamic Meta-Orchestrator

> **Status**: Core backend implementation complete. Dashboard DAG visualization and quality scoring are stretch goals.

- [x] **15.1** — Implement `backend/app/agents/task_architect.py` — `TaskArchitect` plain Python class (creates ADK agents dynamically, is not itself an ADK agent):
  - `analyse_task(task: str) -> PipelineBlueprint` — calls `gemini-2.5-flash` with a structured JSON decomposition prompt; selects stage pattern per stage; falls back to single-stage plan on JSON parse failure
  - `build_pipeline(blueprint) -> Agent` — maps each `TaskStage` to: `ParallelAgent` (parallel), `LoopAgent(max_iterations=N)` (loop), `SequentialAgent` (sequential), bare `LlmAgent` (single); wraps all stages in a top-level `SequentialAgent`
  - `execute_pipeline(blueprint, pipeline) -> str` — runs via `Runner` + `InMemorySessionService`; publishes `pipeline_progress` stage events throughout; returns aggregated text summary
  - `publish_blueprint(blueprint)` → EventBus `{"type": "pipeline_created", "pipeline": {...}}` so dashboard shows the plan before execution starts
  - `publish_stage_update(pipeline_id, stage_name, status, progress)` → EventBus `{"type": "pipeline_progress", "status": "pending|running|completed|failed", "progress": 0.0–1.0}` on every transition
  - `_create_sub_agent(task: SubTask)` — resolves T1 tools via `get_tools_for_capabilities(persona_caps)` + T2 plugin tools from `tools_by_persona` dict; builds focused `LlmAgent`
  - `_build_tool_context()` — generates tool inventory string injected into decomposition prompt so Gemini chooses accurate personas
  - `COMPLEXITY_THRESHOLD = 2` — tasks with fewer sub-tasks than threshold skip the architect
- [x] **15.2** — Data models in `task_architect.py`:
  - `StageType(StrEnum)` — `sequential | parallel | loop | single`
  - `SubTask` dataclass — `id, description, persona_id, instruction`
  - `TaskStage` dataclass — `name, stage_type, tasks: list[SubTask], max_iterations`
  - `PipelineBlueprint` dataclass — `task_description, stages, pipeline_id (uuid hex[:12])`; `total_agents` property; `from_analysis(cls, analysis, task)` constructor; `to_dict()` for WebSocket broadcast
- [x] **15.3** — Pipeline execution patterns all supported:
  - **Sequential** — step-by-step workflows (research → analyse → format)
  - **Parallel** — concurrent gathering with up to 4–6 simultaneous `LlmAgent` nodes
  - **Loop** — iterative refinement with `LoopAgent(max_iterations=N)` (currently runs to max; quality scoring is stretch)
  - **Hybrid** — stages of different types composed into one `SequentialAgent` wrapper
- [x] **15.4** — `backend/app/agents/task_planner_tool.py` — FunctionTool bridge to root agent:
  - `plan_task(task: str, tool_context: ToolContext) -> str` — full pipeline: `analyse_task` → `publish_blueprint` → `build_pipeline` → `execute_pipeline`; returns formatted plan + truncated execution summary (≤4 000 chars)
  - `get_task_planner_tool() -> FunctionTool` — factory used in `root_agent.py`
- [ ] **15.5** — Quality scoring for `LoopAgent` stages *(stretch goal)*:
  - Add `quality_check_instruction` field to `TaskStage`
  - After each loop iteration call Gemini to score output (`0.0–1.0`) and set `should_continue` flag
  - Include `quality_score` and `iteration` in `pipeline_progress` event payload
- [ ] **15.6** — Dashboard DAG visualization *(stretch goal)*:
  - Frontend subscribes to `pipeline_created` + `pipeline_progress` via `useEventSocket`
  - MVP: ordered step-list with status icons (🟡 pending → 🟢 running → ✅ done / 🔴 failed)
  - Full: React Flow DAG with animated edges, parallel nodes laid out side-by-side, loop counter badge
- [ ] **15.7** — Write tests `backend/tests/test_agents/test_task_architect.py`:
  - `test_analyse_task_returns_blueprint` — mock Gemini response, assert `PipelineBlueprint` fields populated correctly
  - `test_build_pipeline_parallel` — stage `type=parallel` → wrapped in `ParallelAgent`
  - `test_build_pipeline_loop` — stage `type=loop, max_iterations=3` → `LoopAgent` with correct max
  - `test_fallback_on_bad_json` — assert single-stage fallback when LLM returns non-JSON text
  - `test_plan_task_tool_publishes_blueprint` — mock `EventBus`, assert `pipeline_created` event emitted with correct `type` field

**Dependencies**: Task 6, Task 7, Task 8
**Files**: `backend/app/agents/task_architect.py`, `backend/app/agents/task_planner_tool.py`, `backend/tests/test_agents/test_task_architect.py`
**Research Refs**: R&P Section 9 (TaskArchitect — Dynamic Meta-Orchestrator: decomposition flow, 5 example pipelines, blueprint JSON schema, actual ADK implementation sketch, EventBus event formats), R&P Section 2 (ADK Agent Types — Sequential, Parallel, Loop), Architecture Plan Steps 7–8
**Verify**: `plan_task` FunctionTool decomposes multi-step request correctly; `pipeline_created` event emitted before execution; `pipeline_progress` events fired per stage; single-step tasks bypass architect

---

### Task 16: Agent Engine Integration (Sessions + Memory Bank)

- [ ] **16.1** — Implement `backend/app/services/memory_service.py` with Vertex AI Agent Engine Memory Bank:
  - `store_memory(user_id, session_id, facts)` — extract and store key facts from conversations
  - `retrieve_memories(user_id, query)` — semantic search across past memories
  - `get_user_context(user_id)` — retrieve all relevant memories for session start
  - Fallback: if Agent Engine unavailable, use Firestore-based simple memory
- [ ] **16.2** — Integrate Memory Bank into agent session startup — inject relevant memories into system prompt
- [ ] **16.3** — Implement `backend/app/services/eval_service.py` with Gen AI Evaluation Service:
  - `evaluate_response(prompt, response, criteria)` — score agent quality
  - `generate_test_cases(persona_config)` — auto-generate persona-specific test cases
- [ ] **16.4** — Write test: `backend/tests/test_services/test_memory_service.py` — test memory storage and retrieval with mock Agent Engine client

**Dependencies**: Task 3, Task 6
**Files**: `backend/app/services/memory_service.py`, `backend/app/services/eval_service.py`, `backend/tests/test_services/test_memory_service.py`
**Research Refs**: GCP Section 4.3 (Memory Bank — semantic search, fact extraction), GCP Section 4.5 (Gen AI Evaluation), GCP Section 4.1 (Agent Engine architecture)
**Verify**: Agent recalls past conversation facts, evaluation scores return for sample prompts

---

### Task 17: Rate Limiting & Error Handling Middleware

- [ ] **17.1** — Implement `backend/app/middleware/rate_limit.py`:
  - Per-user: 100 requests/minute for REST endpoints
  - Per-MCP: 50 calls/minute to prevent abuse
  - WebSocket: unlimited (rate-limited at audio frame level)
  - Return 429 with Retry-After header
- [ ] **17.2** — Implement ADK callbacks for error handling in agent pipeline:
  - `before_model` callback: input sanitization, length check
  - `after_model` callback: response validation, content safety
  - `before_tool` / `after_tool`: MCP failure recovery, timeout handling
  - `on_error`: graceful error messages spoken to user
- [ ] **17.3** — Write test: `backend/tests/test_api/test_rate_limit.py` — test rate limit triggers correctly at threshold

**Dependencies**: Task 1, Task 6
**Files**: `backend/app/middleware/rate_limit.py`, `backend/tests/test_api/test_rate_limit.py`
**Research Refs**: PS Section 8 (Rate Limiting), R&P Section 9 (Callbacks System), R&P Section 12 (Error Handling)
**Verify**: Rate limit triggers at 100 req/min, error callbacks produce spoken error messages

---

### Task 18: Desktop Client Tools

- [ ] **18.1** — Implement `backend/app/mcps/desktop_tools.py` as MCP for desktop automation:
  - `capture_screen()` — request screenshot from desktop client
  - `click_at(x, y)` — click at screen coordinates
  - `type_text(text)` — type text at cursor position
  - `open_application(app_name)` — launch application
  - `manage_files(action, path, content=None)` — read/write/list files on desktop
  - `press_key(key_combo)` — keyboard shortcut (e.g., "ctrl+c")
- [ ] **18.2** — Each tool sends WebSocket command to desktop client_type and awaits response with timeout
- [ ] **18.3** — Write test: `backend/tests/test_tools/test_desktop_tools.py` — test tool command formatting and timeout handling

**Dependencies**: Task 5, Task 12
**Files**: `backend/app/tools/desktop_tools.py`, `backend/tests/test_tools/test_desktop_tools.py`
**Research Refs**: R&P Section 8 (Desktop Client Research — Computer Use, ADK Tools, pyautogui)
**Verify**: Desktop tools send correct WebSocket commands, handle timeout gracefully

---

## Phase 4: Dashboard Foundation (Tasks 19–26)

### Task 19: Dashboard Bootstrap & Theme System

- [ ] **19.1** — Install all dependencies: `pnpm install` in `dashboard/`
- [ ] **19.2** — Initialize shadcn/ui: `npx shadcn@latest init` (configure for Vite + Tailwind CSS 4)
- [ ] **19.3** — Add shadcn/ui primitives: `npx shadcn@latest add button input card dialog dropdown-menu tabs tooltip badge avatar select switch slider skeleton scroll-area separator sheet popover command`
- [ ] **19.4** — Verify `dashboard/src/styles/globals.css` has correct oklch CSS variables for light/dark themes matching spec
- [ ] **19.5** — Implement `dashboard/src/stores/themeStore.js` — Zustand store: `theme` state ('dark'|'light'|'system'), `setTheme()` persisting to localStorage, DOM class toggle
- [ ] **19.6** — Implement `dashboard/src/components/layout/ThemeToggle.jsx` — sun/moon icon button using themeStore
- [ ] **19.7** — Write test: verify theme toggle switches CSS class on document element

**Dependencies**: None (can start in parallel with backend tasks)
**Files**: `dashboard/src/styles/globals.css`, `dashboard/src/stores/themeStore.js`, `dashboard/src/components/layout/ThemeToggle.jsx`
**Research Refs**: PS Section 4 (Design System — OKLCH colors, typography, spacing), PS Section 5 (Component Library — shadcn init)
**Verify**: `pnpm run dev` launches, dark/light theme switches correctly, shadcn components render

---

### Task 20: App Shell & Layout Components

- [ ] **20.1** — Implement `dashboard/src/App.jsx` with React Router v7: routes for `/` (Dashboard), `/personas`, `/mcp-store`, `/sessions`, `/clients`, `/settings`, `*` (404)
- [ ] **20.2** — Implement `dashboard/src/components/layout/AppShell.jsx` — main layout: Sidebar (256px / 64px collapsed) + TopBar (56px) + main content area
- [x] **20.3** — Implement `dashboard/src/components/layout/Sidebar.jsx` — navigation links with Lucide icons, collapse/expand toggle, active route highlighting, keyboard shortcut hints; includes **live client activity dots** next to Clients nav item (green `●` per connected client, up to 3 + overflow count)
- [x] **20.4** — Implement `dashboard/src/components/layout/TopBar.jsx` — app title, UserMenu, ThemeToggle, connected client count badge
- [ ] **20.5** — Implement `dashboard/src/components/layout/MobileNav.jsx` — bottom navigation bar for mobile (< 768px), voice orb center, quick-access buttons
- [ ] **20.6** — Implement `dashboard/src/stores/uiStore.js` — Zustand store: `sidebarOpen`, `commandPaletteOpen`, `activeModals`, `toggleSidebar()`, `openModal()`, `closeModal()`
- [ ] **20.7** — Write test: verify AppShell renders Sidebar + TopBar, route changes show correct page

**Dependencies**: Task 19
**Files**: `dashboard/src/App.jsx`, `dashboard/src/components/layout/AppShell.jsx`, `dashboard/src/components/layout/Sidebar.jsx`, `dashboard/src/components/layout/TopBar.jsx`, `dashboard/src/components/layout/MobileNav.jsx`, `dashboard/src/stores/uiStore.js`
**Research Refs**: PS Section 3 (Frontend Architecture — Routing, Provider Stack), PS Section 4 (Spacing — Sidebar 256px, TopBar 56px), PS Section 11 (Responsive Breakpoints)
**Verify**: Navigation works, sidebar collapses, responsive layout adapts at breakpoints

---

### Task 21: Firebase Auth & Auth Components

- [ ] **21.1** — Implement `dashboard/src/lib/firebase.js` — Firebase SDK initialization with env vars (`VITE_FIREBASE_*`), export `auth`, `db` (Firestore), `storage` instances
- [ ] **21.2** — Implement `dashboard/src/stores/authStore.js` — Zustand store: `user`, `token`, `loading`, `error`, `signInWithGoogle()` (Firebase popup), `signOut()`, `refreshToken()`, auth state listener
- [ ] **21.3** — Implement `dashboard/src/components/auth/LoginPage.jsx` — centered card with Google sign-in button, app logo, tagline
- [ ] **21.4** — Implement `dashboard/src/components/auth/AuthGuard.jsx` — route wrapper that redirects to LoginPage if not authenticated
- [ ] **21.5** — Implement `dashboard/src/components/auth/UserMenu.jsx` — avatar dropdown with user name, email, sign out button
- [ ] **21.6** — Implement `dashboard/src/hooks/useAuth.js` — convenience hook wrapping authStore with auto-token-refresh
- [ ] **21.7** — Write test: verify AuthGuard redirects unauthenticated users, allows authenticated users

**Dependencies**: Task 19, Task 20
**Files**: `dashboard/src/lib/firebase.js`, `dashboard/src/stores/authStore.js`, `dashboard/src/components/auth/LoginPage.jsx`, `dashboard/src/components/auth/AuthGuard.jsx`, `dashboard/src/components/auth/UserMenu.jsx`, `dashboard/src/hooks/useAuth.js`
**Research Refs**: PS Section 8 (Authentication — Firebase Auth, JWT in WS handshake), PS Section 10 (authStore)
**Verify**: Google sign-in flow works, token stored, protected routes guarded

---

### Task 22: WebSocket Connection Hook & Helpers

- [ ] **22.1** — Implement `dashboard/src/lib/ws.js` with WebSocket helper functions:
  - `createWebSocket(url, token)` — create WS connection with auth token in first message
  - `sendJSON(ws, message)` — send JSON control message
  - `sendBinary(ws, audioBuffer)` — send binary audio frame
  - `parseMessage(event)` — parse incoming message (binary = audio, text = JSON)
  - Reconnection with exponential backoff (1s → 2s → 4s → max 30s)
- [x] **22.2** — Implement `dashboard/src/hooks/useWebSocket.js` — React hook:
  - Connects to `ws://host/ws/live` on mount with auth token
  - Handles auth handshake (send auth message, wait for auth_response)
  - Exposes: `sendMessage(msg)`, `sendAudio(buffer)`, `isConnected`, `connectionState`
  - Dispatches received messages to appropriate Zustand stores (chatStore for responses, clientStore for status, etc.)
  - Auto-reconnect on disconnect
  - Cleanup on unmount
- [x] **22.2b** — Implement `dashboard/src/hooks/useChatWebSocket.js` — text-only `/ws/chat` hook for ADK runner (independent of audio live session); same message protocol; includes `sendText()` with optimistic UI and auto-title refresh
- [x] **22.2c** — Implement `dashboard/src/hooks/useEventSocket.js` — read-only `/ws/events` hook for dashboard push notifications (pipeline events, `client_status_update`, `session_suggestion`); routes events to pipelineStore, clientStore, sessionSuggestionStore
- [ ] **22.3** — Write test: verify WebSocket hook connects, authenticates, and dispatches messages to stores

**Dependencies**: Task 19, Task 21
**Files**: `dashboard/src/lib/ws.js`, `dashboard/src/hooks/useWebSocket.js`
**Research Refs**: R&P Section 3 (Gemini Live API — client-side WS), R&P Transport Decision (Raw WebSocket), PS Section 9 (WebSocket Protocol — handshake, message types)
**Verify**: WebSocket connects to backend, auth handshake succeeds, messages route to correct stores

---

### Task 23: Audio Capture & Playback Pipeline

- [ ] **23.1** — Implement `dashboard/src/lib/audio.js` with audio utility functions:
  - `float32ToPCM16(float32Array)` — convert Float32 [-1,1] to Int16 PCM
  - `pcm16ToFloat32(int16Array)` — convert Int16 PCM to Float32 for playback
  - `resample(buffer, fromRate, toRate)` — resample between 16kHz and 24kHz if needed
  - `calculateVolume(pcmData)` — compute RMS volume for meters
- [ ] **23.2** — Implement `dashboard/src/hooks/useAudioCapture.js` — React hook:
  - Uses `AudioWorklet` with 16kHz capture rate
  - Worklet processes Float32 → PCM16 in dedicated thread
  - Streams PCM16 chunks via callback (sent through WebSocket as binary)
  - Exposes: `startCapture()`, `stopCapture()`, `isCapturing`, `volume` (real-time RMS)
  - Permissions handling: request mic, handle denial gracefully
- [ ] **23.3** — Implement `dashboard/src/hooks/useAudioPlayback.js` — React hook:
  - Queue-based playback at 24kHz sample rate
  - Receives PCM16 binary chunks, converts to Float32, plays through AudioContext
  - Handles barge-in: `stopPlayback()` immediately silences with gain ramp-down
  - Stall detection: if queue empties, don't glitch
  - Exposes: `enqueueAudio(pcm16Chunk)`, `stopPlayback()`, `isPlaying`, `volume`
- [ ] **23.4** — Write test: verify `float32ToPCM16` and `pcm16ToFloat32` round-trip correctly

**Dependencies**: Task 19, Task 22
**Files**: `dashboard/src/lib/audio.js`, `dashboard/src/hooks/useAudioCapture.js`, `dashboard/src/hooks/useAudioPlayback.js`
**Research Refs**: R&P Section 3 (Audio Specs — 16kHz/24kHz PCM, AudioWorklet pattern), R&P Section 3.2 (AudioRecorder, AudioStreamer patterns, volume meter)
**Verify**: Mic captures at 16kHz, playback at 24kHz, barge-in silences immediately, no audio glitches

---

### Task 24: Chat UI & Voice Orb

- [ ] **24.1** — Implement `dashboard/src/stores/chatStore.js` — Zustand store: `messages[]`, `currentPersona`, `isRecording`, `isMuted`, `transcription`, `addMessage()`, `updateTranscription()`, `toggleRecord()`, `toggleMute()`, `clearMessages()`
- [ ] **24.2** — Implement `dashboard/src/components/chat/ChatPanel.jsx` — scrollable message list, auto-scroll on new messages, message input at bottom
- [ ] **24.3** — Implement `dashboard/src/components/chat/MessageBubble.jsx` — user vs AI styling, supports text + GenUI embedded content, timestamp, persona avatar
- [ ] **24.4** — Implement `dashboard/src/components/chat/ChatInput.jsx` — text input with send button, mic toggle button, keyboard shortcut (Enter to send, Shift+Enter for newline)
- [ ] **24.5** — Implement `dashboard/src/components/chat/VoiceOrb.jsx` — central pulsing sphere:
  - Idle: subtle breathe animation
  - Recording: pulsing glow synced to mic volume
  - Agent speaking: wave animation synced to playback volume
  - Click to toggle recording, visual state transitions (150ms)
- [ ] **24.6** — Implement `dashboard/src/components/chat/Waveform.jsx` — real-time audio waveform visualization using canvas
- [ ] **24.7** — Implement `dashboard/src/components/chat/TranscriptLine.jsx` — live transcription text with fade-in animation
- [ ] **24.8** — Implement `dashboard/src/components/chat/TypingIndicator.jsx` — animated dots when agent is processing
- [ ] **24.9** — Write test: verify ChatPanel renders messages, VoiceOrb toggles recording state

**Dependencies**: Task 20, Task 22, Task 23
**Files**: `dashboard/src/stores/chatStore.js`, `dashboard/src/components/chat/ChatPanel.jsx`, `dashboard/src/components/chat/MessageBubble.jsx`, `dashboard/src/components/chat/ChatInput.jsx`, `dashboard/src/components/chat/VoiceOrb.jsx`, `dashboard/src/components/chat/Waveform.jsx`, `dashboard/src/components/chat/TranscriptLine.jsx`, `dashboard/src/components/chat/TypingIndicator.jsx`
**Research Refs**: PS Section 6 (DashboardPage — ChatPanel, VoiceOrb, Waveform, audio visual), PS Section 4 (Animations — 150ms button, 200ms transitions)
**Verify**: Messages display correctly, voice orb animates with audio, transcription updates in real-time

---

### Task 25: GenUI Renderer & Dynamic Components

- [ ] **25.1** — Implement `dashboard/src/components/genui/GenUIRenderer.jsx` — component dispatcher: reads `response.content_type` and renders the matching GenUI component
- [ ] **25.2** — Implement `dashboard/src/components/genui/DynamicChart.jsx` — Recharts wrapper supporting line, bar, area, pie charts from agent data
- [ ] **25.3** — Implement `dashboard/src/components/genui/DataTable.jsx` — sortable, filterable table with pagination
- [ ] **25.4** — Implement `dashboard/src/components/genui/InfoCard.jsx` — structured info display card (title, value, icon, trend)
- [ ] **25.5** — Implement `dashboard/src/components/genui/CodeBlock.jsx` — syntax-highlighted code with copy button, language label
- [ ] **25.6** — Implement `dashboard/src/components/genui/ImageGallery.jsx` — grid of generated/fetched images with lightbox
- [ ] **25.7** — Implement `dashboard/src/components/genui/TimelineView.jsx` — chronological event list
- [ ] **25.8** — Implement `dashboard/src/components/genui/MarkdownRenderer.jsx` — react-markdown with remark-gfm, syntax highlighting for code blocks
- [ ] **25.9** — Implement `dashboard/src/components/genui/DiffViewer.jsx` — side-by-side code diff
- [ ] **25.10** — Implement `dashboard/src/components/genui/WeatherWidget.jsx` — weather display card (temp, conditions, forecast)
- [ ] **25.11** — Implement `dashboard/src/components/genui/MapView.jsx` — map component for location-based results
- [ ] **25.12** — Write test: verify GenUIRenderer dispatches to correct component for each content_type

**Dependencies**: Task 19, Task 24
**Files**: `dashboard/src/components/genui/GenUIRenderer.jsx`, `dashboard/src/components/genui/DynamicChart.jsx`, `dashboard/src/components/genui/DataTable.jsx`, `dashboard/src/components/genui/InfoCard.jsx`, `dashboard/src/components/genui/CodeBlock.jsx`, `dashboard/src/components/genui/ImageGallery.jsx`, `dashboard/src/components/genui/TimelineView.jsx`, `dashboard/src/components/genui/MarkdownRenderer.jsx`, `dashboard/src/components/genui/DiffViewer.jsx`, `dashboard/src/components/genui/WeatherWidget.jsx`, `dashboard/src/components/genui/MapView.jsx`
**Research Refs**: R&P Section 9 (GenUI — component mapping, why it matters), PS Section 6 (DashboardPage — GenUI panel)
**Verify**: Each GenUI type renders correctly, charts display with sample data, code blocks highlight syntax

---

### Task 26: Dashboard Main Page Assembly

- [x] **26.1** — Implement `dashboard/src/pages/DashboardPage.jsx` — assemble: ChatPanel (left 60%) + GenUI panel (right 40%) + VoiceOrb overlay
  - Responsive: mobile = full-width chat, GenUI in modal overlay
  - Connect all hooks: useWebSocket, useAudioCapture, useAudioPlayback, useChatWebSocket
  - Wire chatStore: incoming messages → MessageBubble list
  - Wire GenUI: incoming genui responses → GenUIRenderer
  - Wire audio: capture → sendBinary, received audio → enqueueAudio
  - **Voice persona switcher** dropdown in overview sidebar — switch active persona live, auto-reconnects WS
  - **Session suggestion banner** renders when another device has an active session
- [ ] **26.2** — Implement `dashboard/src/hooks/useKeyboard.js` — global keyboard shortcuts:
  - `Ctrl+K` / `Cmd+K`: command palette
  - `Space` (when not in input): toggle recording
  - `Escape`: close modal / stop recording
  - `Ctrl+M`: toggle mute
- [ ] **26.3** — Write test: verify DashboardPage renders ChatPanel and GenUI panel side-by-side

**Dependencies**: Task 22, Task 23, Task 24, Task 25
**Files**: `dashboard/src/pages/DashboardPage.jsx`, `dashboard/src/hooks/useKeyboard.js`
**Research Refs**: PS Section 6 (DashboardPage — layout, responsiveness), PS Section 11 (Responsive Breakpoints, Keyboard Navigation)
**Verify**: Full dashboard renders with chat + GenUI, audio flows end-to-end, keyboard shortcuts work

---

## Phase 5: Dashboard Feature Pages (Tasks 27–31)

### Task 27: Personas Page & Components

- [ ] **27.1** — Implement `dashboard/src/stores/personaStore.js` — Zustand store: `personas[]`, `activePersonaId`, `fetchPersonas()`, `createPersona()`, `updatePersona()`, `deletePersona()`, `switchPersona()`
- [ ] **27.2** — Implement `dashboard/src/components/persona/PersonaCard.jsx` — card displaying: avatar, name, voice, description, active indicator, click to activate
- [ ] **27.3** — Implement `dashboard/src/components/persona/PersonaList.jsx` — grid of PersonaCards with "Create New" button
- [ ] **27.4** — Implement `dashboard/src/components/persona/PersonaEditor.jsx` — modal/sheet form: name, voice dropdown (8 voices), system instruction textarea, MCP multi-select, avatar upload
- [ ] **27.5** — Implement `dashboard/src/components/persona/VoicePreview.jsx` — play sample audio of selected voice
- [ ] **27.6** — Implement `dashboard/src/pages/PersonasPage.jsx` — PersonaList + PersonaEditor integration, CRUD operations wired to backend API
- [ ] **27.7** — Implement `dashboard/src/lib/api.js` — fetch wrapper:
  - `apiGet(path)`, `apiPost(path, body)`, `apiPut(path, body)`, `apiDelete(path)` 
  - Auto-attaches Firebase auth token
  - Handles 401 (refresh token + retry), 429 (rate limit message)
  - Base URL from `VITE_API_URL` env var
- [ ] **27.8** — Write test: verify PersonaCard renders persona data, PersonaEditor validates required fields

**Dependencies**: Task 20, Task 21
**Files**: `dashboard/src/stores/personaStore.js`, `dashboard/src/components/persona/PersonaCard.jsx`, `dashboard/src/components/persona/PersonaList.jsx`, `dashboard/src/components/persona/PersonaEditor.jsx`, `dashboard/src/components/persona/VoicePreview.jsx`, `dashboard/src/pages/PersonasPage.jsx`, `dashboard/src/lib/api.js`
**Research Refs**: PS Section 6 (PersonasPage — grid, editor, voice preview), PS Section 10 (personaStore), R&P Section 3 (8 voice names)
**Verify**: Personas CRUD works end-to-end, voice preview plays, active persona highlighted

---

### Task 28: MCP Store Page & Components

- [ ] **28.1** — Implement `dashboard/src/stores/mcpStore.js` — Zustand store: `enabledMCPs[]`, `allMCPs[]`, `categories[]`, `toggleMCP()`, `fetchCatalog()`, `fetchEnabledMCPs()`
- [ ] **28.2** — Implement `dashboard/src/components/mcp/MCPStoreGrid.jsx` — grid of MCP cards filtered by category, search bar
- [ ] **28.3** — Implement `dashboard/src/components/mcp/MCPCard.jsx` — card: icon, name, description, category badge, enabled toggle switch
- [ ] **28.4** — Implement `dashboard/src/components/mcp/MCPDetail.jsx` — sheet/modal: full description, tools list, auth requirements, usage examples
- [ ] **28.5** — Implement `dashboard/src/components/mcp/MCPCategoryNav.jsx` — horizontal category tabs (Development, Productivity, Search, Data, Automation, etc.)
- [ ] **28.6** — Implement `dashboard/src/components/mcp/MCPToggle.jsx` — toggle switch with confirmation for auth-required MCPs
- [ ] **28.7** — Implement `dashboard/src/pages/MCPStorePage.jsx` — assemble grid + category nav + detail sheet + search
- [ ] **28.8** — Write test: verify MCPCard renders MCP data, toggle dispatches store action

**Dependencies**: Task 20, Task 21, Task 27 (api.js)
**Files**: `dashboard/src/stores/mcpStore.js`, `dashboard/src/components/mcp/MCPStoreGrid.jsx`, `dashboard/src/components/mcp/MCPCard.jsx`, `dashboard/src/components/mcp/MCPDetail.jsx`, `dashboard/src/components/mcp/MCPCategoryNav.jsx`, `dashboard/src/components/mcp/MCPToggle.jsx`, `dashboard/src/pages/MCPStorePage.jsx`
**Research Refs**: PS Section 6 (MCPStorePage — grid, detail, categories), PS Section 10 (mcpStore), R&P Section 7 (Trending MCPs — catalog items)
**Verify**: MCP catalog loads, enable/disable toggles update backend, categories filter correctly

---

### Task 29: Sessions Page & Components

- [x] **29.1** — Implement `dashboard/src/stores/sessionStore.js` — Zustand store: `sessions[]`, `currentSessionId`, `isLoading`, `loadSessions()`, `createSession()`, `switchSession()`, `deleteSession()`, `ensureSession()`, `setActiveSession()`, `setWantsNewSession()`; **session title auto-generation**: backend generates ≤6-word title from first user message via Gemini, frontend refreshes session list 4s after first send
- [ ] **29.2** — Implement `dashboard/src/components/session/SessionList.jsx` — sidebar list: date groups, title snippet, last message time, delete/export hover actions
- [ ] **29.3** — Implement `dashboard/src/components/session/SessionItem.jsx` — individual session entry with active highlight
- [ ] **29.4** — Implement `dashboard/src/components/session/SessionSearch.jsx` — full-text search across conversation history
- [ ] **29.5** — Implement `dashboard/src/pages/SessionsPage.jsx` — SessionList sidebar + conversation detail center panel, showing full message history with timestamps, personas used, MCPs called
- [ ] **29.6** — Write test: verify SessionList renders sessions sorted by date, search filters correctly

**Dependencies**: Task 20, Task 21, Task 27 (api.js)
**Files**: `dashboard/src/stores/sessionStore.js`, `dashboard/src/components/session/SessionList.jsx`, `dashboard/src/components/session/SessionItem.jsx`, `dashboard/src/components/session/SessionSearch.jsx`, `dashboard/src/pages/SessionsPage.jsx`
**Research Refs**: PS Section 6 (SessionsPage — list, search, detail), PS Section 10 (sessionStore)
**Verify**: Sessions load from backend, switching sessions changes chat history, search works

---

### Task 30: Clients Page & Status Components

- [ ] **30.1** — Implement `dashboard/src/stores/clientStore.js` — Zustand store: `connectedClients[]`, `watchConnectedClients()` (real-time Firestore listener)
- [ ] **30.2** — Implement `dashboard/src/components/clients/ClientCard.jsx` — card: device type icon (desktop/chrome/mobile/glasses), name, connected time, last activity, status indicator
- [ ] **30.3** — Implement `dashboard/src/components/clients/ClientList.jsx` — grid of connected client cards
- [ ] **30.4** — Implement `dashboard/src/components/clients/ClientStatusBar.jsx` — sticky bar showing all active clients with count badge, real-time updates
- [ ] **30.5** — Implement `dashboard/src/pages/ClientsPage.jsx` — ClientList with device-specific info on click
- [ ] **30.6** — Implement `dashboard/src/hooks/useFirestore.js` — real-time Firestore listener hook for client status changes
- [ ] **30.7** — Write test: verify ClientCard renders client data, ClientStatusBar shows correct count

**Dependencies**: Task 20, Task 21
**Files**: `dashboard/src/stores/clientStore.js`, `dashboard/src/components/clients/ClientCard.jsx`, `dashboard/src/components/clients/ClientList.jsx`, `dashboard/src/components/clients/ClientStatusBar.jsx`, `dashboard/src/pages/ClientsPage.jsx`, `dashboard/src/hooks/useFirestore.js`
**Research Refs**: PS Section 6 (ClientsPage — grid, status bar), PS Section 10 (clientStore — Firestore listener)
**Verify**: Connected clients appear in real-time, disconnected clients update status, count badge accurate

---

### Task 31: Settings Page & Sandbox Console

- [ ] **31.1** — Implement `dashboard/src/pages/SettingsPage.jsx` with tabs:
  - **General**: theme selector, language, notification preferences
  - **Privacy**: data retention toggle, analytics opt-out
  - **Integrations**: API key inputs for MCP auth (encrypted storage)
  - **Shortcuts**: keyboard binding display and customization
- [ ] **31.2** — Implement `dashboard/src/components/sandbox/SandboxConsole.jsx` — terminal-like output for code execution results (stdout/stderr), auto-scroll, copy output
- [ ] **31.3** — Implement `dashboard/src/components/sandbox/CodeEditor.jsx` — code input area with syntax highlighting, language selector, run button
- [ ] **31.4** — Implement `dashboard/src/components/sandbox/FileExplorer.jsx` — tree view of sandbox files, click to view, download option
- [ ] **31.5** — Write test: verify SettingsPage tabs render, SandboxConsole displays output correctly

**Dependencies**: Task 20, Task 21
**Files**: `dashboard/src/pages/SettingsPage.jsx`, `dashboard/src/components/sandbox/SandboxConsole.jsx`, `dashboard/src/components/sandbox/CodeEditor.jsx`, `dashboard/src/components/sandbox/FileExplorer.jsx`
**Research Refs**: PS Section 6 (SettingsPage tabs), R&P Section 4 (E2B — sandbox file operations)
**Verify**: Settings persist, sandbox console shows code output, file explorer navigates

---

## Phase 6: Desktop Client & Chrome Extension (Tasks 32–34)

### Task 32: Desktop Client — Python Tray App

- [ ] **32.1** — Implement `desktop-client/src/config.py` — configuration: server URL, auth token path, capture settings, hotkeys
- [ ] **32.2** — Implement `desktop-client/src/ws_client.py` — WebSocket client:
  - Connect to backend `ws://host/ws/live`
  - Send auth message with stored token
  - Receive commands from agent (screenshot, click, type, open app)
  - Send responses back (screenshot data, action result)
  - Auto-reconnect with exponential backoff
- [ ] **32.3** — Implement `desktop-client/src/screen.py` — screen capture:
  - `capture_screenshot()` — full screen or specific window via Pillow
  - `capture_region(x, y, w, h)` — specific screen region
  - Compress to JPEG, encode base64, send via WebSocket
- [ ] **32.4** — Implement `desktop-client/src/actions.py` — desktop automation:
  - `click_at(x, y)` — mouse click via pyautogui
  - `type_text(text)` — keyboard input
  - `press_key(key_combo)` — keyboard shortcuts
  - `open_application(name)` — launch app (platform-specific)
  - `get_window_info()` — active window title, size, position
- [ ] **32.5** — Implement `desktop-client/src/files.py` — file operations:
  - `read_file(path)`, `write_file(path, content)`, `list_directory(path)`
  - Security: restrict to user's home directory, deny system paths
- [ ] **32.6** — Implement `desktop-client/src/main.py` — system tray app:
  - pystray icon with menu (Connect, Disconnect, Settings, Quit)
  - Status indicator (connected/disconnected)
  - Global hotkey to trigger voice (optional)
  - Starts ws_client on launch
- [ ] **32.7** — Write test: `desktop-client/tests/test_actions.py` — test click_at, type_text, press_key with mock pyautogui

**Dependencies**: Task 7 (backend WebSocket working)
**Files**: `desktop-client/src/config.py`, `desktop-client/src/ws_client.py`, `desktop-client/src/screen.py`, `desktop-client/src/actions.py`, `desktop-client/src/files.py`, `desktop-client/src/main.py`, `desktop-client/tests/test_actions.py`
**Research Refs**: R&P Section 8 (Desktop Client Research — pystray, pyautogui, Computer Use architecture, ADK tools)
**Verify**: Tray app starts, connects to backend, receives screenshot command, returns screenshot

---

### Task 33: Chrome Extension — Manifest V3

- [ ] **33.1** — Implement `chrome-extension/manifest.json` — MV3 manifest with permissions: activeTab, tabs, scripting, storage, offscreen, sidePanel
- [ ] **33.2** — Implement `chrome-extension/background.js` — service worker:
  - WebSocket connection to backend `ws://host/ws/live`
  - Auth with stored Firebase token
  - Receive commands from agent (open tab, click element, read page, navigate)
  - Route commands to content script
  - Handle offscreen document for audio (if needed)
- [ ] **33.3** — Implement `chrome-extension/content.js` — content script:
  - `clickElement(selector)` — click DOM element
  - `readPageContent()` — extract page text
  - `fillInput(selector, value)` — fill form fields
  - `getPageInfo()` — title, URL, meta description
  - `scrollTo(selector)` — scroll to element
  - Communication with background.js via `chrome.runtime.sendMessage`
- [ ] **33.4** — Implement `chrome-extension/popup/popup.html` + `popup.js` + `popup.css` — extension popup:
  - Connection status indicator
  - Active persona display
  - Quick voice command button
  - Settings link (server URL, auth)
- [ ] **33.5** — Implement `chrome-extension/offscreen/offscreen.html` + `offscreen.js` — offscreen document for audio capture in MV3 (AudioWorklet not available in service worker)
- [ ] **33.6** — Write test: verify content.js command routing (mock chrome.runtime API)

**Dependencies**: Task 7 (backend WebSocket working)
**Files**: `chrome-extension/manifest.json`, `chrome-extension/background.js`, `chrome-extension/content.js`, `chrome-extension/popup/popup.html`, `chrome-extension/popup/popup.js`, `chrome-extension/popup/popup.css`, `chrome-extension/offscreen/offscreen.html`, `chrome-extension/offscreen/offscreen.js`
**Research Refs**: R&P Section 6 (Chrome Extension — WebMCP, DevTools MCP, 45+ voice commands), R&P Section 6.5 (Voice-Activated Tasks)
**Verify**: Extension loads in Chrome, connects to backend, executes page commands

---

### Task 34: Not Found Page & Shared Components

- [ ] **34.1** — Implement `dashboard/src/pages/NotFoundPage.jsx` — 404 page with illustration and "Go Home" button
- [ ] **34.2** — Implement shared utility components in `dashboard/src/components/shared/`:
  - `LoadingSpinner.jsx` — centered spinner with optional message
  - `ErrorBoundary.jsx` — React error boundary with fallback UI
  - `EmptyState.jsx` — "No data" placeholder with icon and message
  - `ConfirmDialog.jsx` — reusable confirm/cancel dialog
  - `SearchInput.jsx` — debounced search input with clear button
  - `StatusBadge.jsx` — colored badge (online/offline/error)
  - `Kbd.jsx` — keyboard shortcut display component
- [ ] **34.3** — Implement `dashboard/src/hooks/useMediaQuery.js` — responsive breakpoint hook
- [ ] **34.4** — Implement `dashboard/src/lib/formatters.js` — utility functions: `formatDate()`, `formatDuration()`, `formatFileSize()`, `truncateText()`
- [ ] **34.5** — Implement `dashboard/src/lib/constants.js` — app constants: WS_URL, API_URL, VOICE_NAMES, MCP_CATEGORIES, KEYBOARD_SHORTCUTS
- [ ] **34.6** — Implement `dashboard/src/lib/cn.js` — `cn()` utility using `clsx` + `tailwind-merge`
- [ ] **34.7** — Write test: verify formatters return expected output for sample inputs

**Dependencies**: Task 19
**Files**: `dashboard/src/pages/NotFoundPage.jsx`, `dashboard/src/components/shared/*`, `dashboard/src/hooks/useMediaQuery.js`, `dashboard/src/lib/formatters.js`, `dashboard/src/lib/constants.js`, `dashboard/src/lib/cn.js`
**Research Refs**: PS Section 5 (Component Library), PS Section 4 (Design System)
**Verify**: 404 page renders, shared components reusable, formatters correct

---

## Phase 7: Deployment & Infrastructure (Tasks 35–37)

### Task 35: Docker & Docker Compose

- [ ] **35.1** — Finalize `backend/Dockerfile`:
  - Base: `python:3.12-slim`
  - Install `uv`, copy `pyproject.toml` + `uv.lock`, install deps
  - Copy app code, expose port 8080
  - Healthcheck: `CMD curl -f http://localhost:8080/health`
  - Non-root user
- [ ] **35.2** — Finalize `deploy/docker-compose.yml`:
  - `backend` service: build from `backend/`, port 8000:8080, env_file, healthcheck
  - `dashboard` service: build from `dashboard/` (Nginx serving built assets), port 5173:80
  - `firestore-emulator` service: for local development
  - Shared network, volumes for persistent data
- [ ] **35.3** — Write test: `docker build` succeeds for backend, healthcheck passes

**Dependencies**: Task 1
**Files**: `backend/Dockerfile`, `deploy/docker-compose.yml`
**Research Refs**: R&P Section 11 (Tech Stack — Docker, Cloud Run), PS Section 12 (Local Development)
**Verify**: `docker-compose up` starts both services, health checks pass, WebSocket connects

---

### Task 36: Terraform Infrastructure as Code

- [ ] **36.1** — Finalize `deploy/terraform/main.tf`:
  - **Cloud Run** service for backend (min 0, max 10 instances, 2GB RAM, 2 vCPU)
  - **Firestore** database (Native mode, nam5 location)
  - **Cloud Storage** bucket for artifacts (user uploads, generated images)
  - **Secret Manager** secrets for API keys (E2B, Firebase service account)
  - **Artifact Registry** repository for Docker images
  - **Firebase Hosting** site for dashboard
  - **Cloud Logging** + **Cloud Monitoring** + **Cloud Trace** enabled
  - IAM bindings: Cloud Run service account → Firestore, GCS, Secret Manager access
- [ ] **36.2** — Finalize `deploy/terraform/variables.tf`: project_id, region, environment, image_tag, domain
- [ ] **36.3** — Finalize `deploy/terraform/outputs.tf`: service_url, firestore_id, bucket_name, hosting_url
- [ ] **36.4** — Write deploy script: `deploy/scripts/deploy.sh` — build Docker image, push to Artifact Registry, terraform apply
- [ ] **36.5** — Write setup script: `deploy/scripts/setup-env.sh` — create .env files, enable GCP APIs, create service accounts
- [ ] **36.6** — Write test: `terraform validate` passes, `terraform plan` shows expected resources

**Dependencies**: Task 35
**Files**: `deploy/terraform/main.tf`, `deploy/terraform/variables.tf`, `deploy/terraform/outputs.tf`, `deploy/scripts/deploy.sh`, `deploy/scripts/setup-env.sh`
**Research Refs**: GCP (All 21 services listed), R&P Section 12 (Bonus — Automated Deployment +0.2)
**Verify**: `terraform plan` shows all resources, `deploy.sh` runs end-to-end

---

### Task 37: Cloud Observability (Logging + Monitoring + Tracing)

- [ ] **37.1** — Integrate Cloud Logging in backend: structlog → google-cloud-logging handler, request_id in all logs
- [ ] **37.2** — Integrate Cloud Trace: OpenTelemetry spans for WebSocket lifecycle, agent execution, tool calls, MCP operations
- [ ] **37.3** — Integrate Cloud Monitoring: custom metrics — active_sessions gauge, audio_latency_ms histogram, tool_call_success_rate counter
- [ ] **37.4** — Create monitoring dashboard config (for demo): active sessions, latency p99, error rate
- [ ] **37.5** — Write test: verify log entries contain expected fields (request_id, user_id, action)

**Dependencies**: Task 1, Task 7
**Files**: `backend/app/utils/logging.py` (enhance), new `backend/app/utils/tracing.py`, new `backend/app/utils/metrics.py`
**Research Refs**: GCP (Observability Layer — Cloud Logging, Cloud Monitoring, Cloud Trace), R&P Section 12 (Demo — Cloud proof)
**Verify**: Logs appear in Cloud Logging console, traces visible in Cloud Trace, metrics in Monitoring

---

## Phase 8: Polish, Demo & Submission (Tasks 38–42)

### Task 38: End-to-End Integration Testing

- [ ] **38.1** — Test full voice pipeline: mic → WebSocket → ADK → Gemini Live → WebSocket → speaker
- [ ] **38.2** — Test persona switching mid-conversation: voice changes, instruction changes, tool changes
- [ ] **38.3** — Test MCP toggle mid-conversation: enable search MCP → agent gains search capability
- [ ] **38.4** — Test cross-client action: send command to desktop → desktop executes → result in dashboard
- [ ] **38.5** — Test GenUI rendering: agent returns chart data → dashboard renders chart while speaking
- [ ] **38.6** — Test error recovery: disconnect WebSocket → auto-reconnect → session resumes
- [ ] **38.7** — Test barge-in: interrupt agent mid-speech → agent stops → processes new input
- [ ] **38.8** — Test memory recall: previous conversation fact → new session → agent remembers

**Dependencies**: All previous tasks
**Research Refs**: R&P Section 12 (Demo Script — "Holy Crap" moments), HACKATHON_BRIEF (Judging — "The Proof")
**Verify**: All 8 scenarios pass without errors

---

### Task 39: Performance Optimization

- [ ] **39.1** — Frontend code splitting: React.lazy + Suspense for each route page
- [ ] **39.2** — Frontend bundle analysis: ensure initial JS < 150KB
- [ ] **39.3** — Audio latency measurement: end-to-end (mic → response audio starts) target < 2s
- [ ] **39.4** — WebSocket frame optimization: binary audio only (no base64 wrapping)
- [ ] **39.5** — Firestore query optimization: compound indexes on frequently queried fields

**Dependencies**: Task 26, Task 35
**Research Refs**: PS Section 12 (Performance Guidelines — code splitting, bundle target, LCP)
**Verify**: Lighthouse score 90+, audio latency < 2s, bundle < 150KB initial

---

### Task 40: Architecture Diagram

- [ ] **40.1** — Create professional architecture diagram showing:
  - All 5 client types connecting via WebSocket to Cloud Run backend
  - Backend components: FastAPI, ADK Runner, MCPManager, E2B Service, Client Registry
  - GCP services: Firestore, GCS, Secret Manager, Cloud Logging/Monitoring/Trace
  - Vertex AI services: Gemini Live API, Agent Engine, Imagen 4, RAG Engine
  - Audio flow: 16kHz in → 24kHz out
  - Cross-client action flow arrows
- [ ] **40.2** — Export as PNG: `docs/architecture.png`
- [ ] **40.3** — Include in README.md

**Dependencies**: All architecture decisions finalized
**Files**: `docs/architecture.png`, `README.md`
**Research Refs**: HACKATHON_BRIEF (Submission Checklist — Architecture Diagram), R&P Section 9 (System Architecture)
**Verify**: Diagram clearly shows all components, readable at presentation size

---

### Task 41: Demo Video (4 Minutes)

- [ ] **41.1** — Script the 4-minute demo:
  - **0:00-0:30**: Problem hook — "AI assistants are trapped in one device, one mode, one text box"
  - **0:30-1:00**: Solution reveal — architecture diagram, multi-client hub, MCP store
  - **1:00-1:30**: Live Demo #1 — Voice conversation + GenUI chart renders simultaneously
  - **1:30-2:00**: Live Demo #2 — Persona switch (voice changes), code execution in sandbox
  - **2:00-2:30**: Live Demo #3 — MCP toggle (capability changes mid-conversation)
  - **2:30-2:45**: Live Demo #4 — Cross-client action (desktop screenshot → analysis in dashboard)
  - **2:45-3:15**: Cloud proof — Cloud Run console, Firestore collections, Cloud Logging traces
  - **3:15-3:35**: Error recovery demo — disconnect + auto-reconnect + session resume
  - **3:35-4:00**: Close — Vision, architecture recap, "Speak anywhere. Act everywhere."
- [ ] **41.2** — Record with clear audio, English narration
- [ ] **41.3** — Upload to YouTube/Vimeo (public link)

**Dependencies**: Task 38
**Research Refs**: R&P Section 12 (Demo Script — 4-min breakdown, "Holy Crap" moments), HACKATHON_BRIEF (Demo & Presentation 30%)
**Verify**: Video ≤ 4 minutes, shows actual working software, all 4 wow moments included

---

### Task 42: Submission Package

- [ ] **42.1** — Finalize `README.md`:
  - Project description (1 paragraph)
  - Architecture diagram embed
  - Features list (bullet points)
  - Tech stack table
  - Quick start (local): `docker-compose up` or manual setup
  - Cloud deployment: `terraform apply`
  - Demo video link
  - Team members
- [ ] **42.2** — Ensure all `.env.example` files are complete (root, backend, dashboard)
- [ ] **42.3** — Create seed data script: `deploy/scripts/seed-data.sh` — populate 5 default personas, MCP catalog, sample session
- [ ] **42.4** — Verify public GitHub repo: all code committed, no secrets, clear README
- [ ] **42.5** — Write blog post for bonus points (+0.6): architecture decisions, code snippets, lessons learned, #GeminiLiveAgentChallenge
- [ ] **42.6** — Verify GDG membership for bonus (+0.2)
- [ ] **42.7** — Submit on Devpost: category (Live Agents), description, repo URL, video URL, deployment proof, architecture diagram

**Dependencies**: All tasks complete
**Research Refs**: HACKATHON_BRIEF (Submission Checklist — all 7 requirements), R&P Section 12 (Bonus Points)
**Verify**: All 7 submission requirements met, bonus content published

---

## Summary: Task Count by Phase

| Phase | Tasks | Description |
|-------|-------|-------------|
| Phase 1 | 1–8 | Backend Core Foundation |
| Phase 2 | 9–14 | Backend Tools & Integrations |
| Phase 3 | 15–18 | Backend Advanced Features |
| Phase 4 | 19–26 | Dashboard Foundation |
| Phase 5 | 27–31 | Dashboard Feature Pages |
| Phase 6 | 32–34 | Desktop Client & Chrome Extension |
| Phase 7 | 35–37 | Deployment & Infrastructure |
| Phase 8 | 38–42 | Polish, Demo & Submission |
| **Total** | **42 Tasks** | **~200 Sub-tasks** |

---

## Parallelization Guide

These task groups can run in parallel:

| Stream | Tasks | Owner |
|--------|-------|-------|
| **Backend Core** | 1→2→3→4→5→6→7→8 | Dev A |
| **Backend Tools** | 9→10→11→12→13→14 (after Task 6) | Dev A |
| **Dashboard UI** | 19→20→21→22→23→24→25→26 | Dev B |
| **Dashboard Pages** | 27→28→29→30→31→34 (after Task 20) | Dev C |
| **Clients** | 32→33 (after Task 7) | Dev D |
| **Infrastructure** | 35→36→37 (after Task 1) | Dev E |

---

## Quick Reference: Key Model Names & Versions

| Component | Value |
|-----------|-------|
| Live Audio Model | `gemini-live-2.5-flash-native-audio` |
| Text/Routing Model | `gemini-2.5-flash` |
| Image Generation | Imagen 4 via Vertex AI |
| Audio Input | 16-bit PCM, 16kHz, mono |
| Audio Output | 16-bit PCM, 24kHz, mono |
| ADK Version | `>= 0.5.0` |
| Voices | Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, Zephyr |
| Firebase Auth | Google sign-in (popup) |
| MCP Protocol | StreamableHTTP (remote), Stdio (local) |
