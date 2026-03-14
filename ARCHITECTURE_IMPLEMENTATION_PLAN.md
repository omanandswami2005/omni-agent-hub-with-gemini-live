# Architecture Redesign: Capability-Based Multi-Layer Agent System

## Overview
Redesign the agent architecture from a flat root→persona model with hardcoded tool sets to a 3-layer capability-based system with dynamic tool matching.

**Current:** Root → 5 flat personas (all get same T2/T3 tools, T1 tools hardcoded by persona ID sets)
**Target:** Root (classify & route) → Layer 1 (Persona Pool) / Layer 2 (TaskArchitect) / Layer 3 (Cross-Client Orchestrator)

---

## Checklist

### Step 1: Add `ToolCapability` Enum
**File:** `backend/app/models/plugin.py`
**What:** Create a predefined set of capability tags used by both tools and personas.

```python
class ToolCapability(StrEnum):
    """Predefined capability tags for tool↔persona matching."""
    SEARCH = "search"
    CODE_EXECUTION = "code_execution"
    KNOWLEDGE = "knowledge"
    CREATIVE = "creative"
    COMMUNICATION = "communication"
    WEB = "web"
    SANDBOX = "sandbox"
    DATA = "data"
    MEDIA = "media"
    DEVICE = "device"       # cross-client / OS-level T3 tools
    WILDCARD = "*"          # matches ALL personas
```

- [x] Add `ToolCapability` enum to `app/models/plugin.py`
- [x] Add `tags: list[str]` field to `PluginManifest` with default `[]`

---

### Step 2: Add `capabilities` to Persona Models
**Files:** `backend/app/models/persona.py`, `backend/app/agents/personas.py`
**What:** Each persona declares which capabilities it needs. Tool registry matches tools by tag intersection.

```python
# persona.py — PersonaCreate
class PersonaCreate(BaseModel):
    name: str
    voice: str = "Kore"
    system_instruction: str = ""
    mcp_ids: list[str] = []
    avatar_url: str = ""
    capabilities: list[str] = []  # NEW — e.g. ["search", "code_execution"]

# persona.py — PersonaResponse
class PersonaResponse(BaseModel):
    id: str
    user_id: str
    name: str
    voice: str = "Kore"
    system_instruction: str = ""
    mcp_ids: list[str] = []
    avatar_url: str = ""
    is_default: bool = False
    created_at: Optional[datetime] = None
    capabilities: list[str] = []  # NEW
```

Default personas get capabilities:
```python
# personas.py
{
    "id": "assistant",
    "capabilities": ["search", "web", "knowledge", "communication", "media"],
},
{
    "id": "coder",
    "capabilities": ["code_execution", "sandbox", "search", "web"],
},
{
    "id": "researcher",
    "capabilities": ["search", "web", "knowledge"],
},
{
    "id": "analyst",
    "capabilities": ["code_execution", "sandbox", "search", "data", "web"],
},
{
    "id": "creative",
    "capabilities": ["creative", "media"],
},
```

- [x] Add `capabilities: list[str] = []` to `PersonaCreate`
- [x] Add `capabilities: list[str] = []` to `PersonaUpdate`
- [x] Add `capabilities: list[str] = []` to `PersonaResponse`
- [x] Add `capabilities` to each entry in `DEFAULT_PERSONAS`

---

### Step 3: Tag T1 Tools with Capabilities
**File:** `backend/app/agents/agent_factory.py`
**What:** Replace hardcoded `_SEARCH_PERSONA_IDS`, `_CODE_EXEC_PERSONA_IDS`, `_IMAGE_GEN_PERSONA_IDS` sets with a registry that maps capabilities → tool factory functions.

```python
# New approach — map capability tags to tool factory functions
from app.models.plugin import ToolCapability as TC

# Tag → factory function that returns list of tools
T1_TOOL_REGISTRY: dict[str, Callable[[], list]] = {
    TC.SEARCH: lambda: [get_search_tool()],
    TC.CODE_EXECUTION: get_code_exec_tools,
    TC.MEDIA: get_image_gen_tools,
    # TC.DEVICE tools go to cross-client orchestrator only — NOT in persona pool
}

def get_tools_for_capabilities(capabilities: list[str]) -> list:
    """Return T1 tools matching any of the given capabilities."""
    tools: list = []
    seen = set()
    for cap in capabilities:
        factory = T1_TOOL_REGISTRY.get(cap)
        if factory and cap not in seen:
            seen.add(cap)
            tools.extend(factory())
    return tools
```

- [x] Create `T1_TOOL_REGISTRY` mapping in `agent_factory.py`
- [x] Create `get_tools_for_capabilities()` function
- [x] Remove `_SEARCH_PERSONA_IDS`, `_CODE_EXEC_PERSONA_IDS`, `_IMAGE_GEN_PERSONA_IDS`
- [x] Update `_default_tools_for_persona()` → use `get_tools_for_capabilities()`

---

### Step 4: Tag T2 Plugins with Capabilities
**Files:** All plugin MANIFEST definitions + `plugin_registry.py` builtin catalog
**What:** Add `tags` to every plugin manifest.

```python
# Built-in catalog tags in plugin_registry.py:
"e2b-sandbox"           → tags: ["code_execution", "sandbox"]
"filesystem"            → tags: ["code_execution", "sandbox"]
"brave-search"          → tags: ["search", "web"]
"github"                → tags: ["code_execution"]
"playwright"            → tags: ["web"]
"notion"                → tags: ["knowledge", "communication"]
"slack"                 → tags: ["communication"]

# Native plugins in app/plugins/:
"notification-sender"   → tags: ["communication"]   + WILDCARD? or just communication
"rag-documents"         → tags: ["knowledge"]
"wikipedia"             → tags: ["search", "knowledge"]
```

- [x] Add `tags` to each builtin in `_builtin_plugins()` in `plugin_registry.py`
- [x] Add `tags` to `notification_sender.py` MANIFEST
- [x] Add `tags` to `rag_plugin.py` MANIFEST
- [x] Add `tags` to `wikipedia_search.py` MANIFEST

---

### Step 5: Refactor `ToolRegistry.build_for_session()` → Return Per-Persona Tool Dict
**File:** `backend/app/services/tool_registry.py`
**What:** Instead of returning a flat list, return a `dict[str, list]` keyed by persona ID. T3 tools go to a separate "device" key.

```python
async def build_for_session(
    self,
    user_id: str,
    personas: list[PersonaResponse],
) -> dict[str, list]:
    """Build per-persona tool lists using capability tag matching.

    Returns: {"assistant": [...tools], "coder": [...tools], "__device__": [...t3 tools]}
    """
    # Load all T2 plugin tools with their tags
    plugin_registry = get_plugin_registry()
    tagged_t2: list[tuple[list[str], list]] = []  # (tags, tools)
    for plugin_id in plugin_registry.get_enabled_ids(user_id):
        manifest = plugin_registry.get_manifest(plugin_id)
        if manifest:
            tools = await plugin_registry.get_tools_for_plugin(user_id, plugin_id)
            tagged_t2.append((manifest.tags, tools))

    # Match T2 tools to personas by capability intersection
    result: dict[str, list] = {}
    for persona in personas:
        matched: list = []
        for tags, tools in tagged_t2:
            if "*" in tags or set(tags) & set(persona.capabilities):
                matched.extend(tools)
        result[persona.id] = matched

    # T3 tools always go to dedicated __device__ bucket
    t3_tools = self._build_t3_tools(user_id)
    if t3_tools:
        result["__device__"] = t3_tools

    return result
```

- [x] Change `build_for_session()` signature to accept `personas` list
- [x] Return `dict[str, list]` instead of flat `list`
- [x] Match T2 tools using tag intersection with persona capabilities
- [x] Separate T3 tools into `__device__` key

---

### Step 6: Create Cross-Client Orchestrator Sub-Agent
**File:** `backend/app/agents/cross_client_agent.py` (NEW)
**What:** A dedicated sub-agent that holds cross-client + T3 tools. Root routes device actions here.

```python
from google.adk.agents import Agent
from app.tools.cross_client import get_cross_client_tools

CROSS_CLIENT_INSTRUCTION = (
    "You are the Cross-Client Orchestrator. You handle actions that involve "
    "connected devices: desktop, Chrome extension, mobile, etc.\n"
    "You have tools to send actions to connected clients and proxy tools "
    "that run on those clients.\n"
    "Available actions: screenshot, click, type, file operations, "
    "browser navigation, notifications.\n"
    "Always confirm which client the user wants to target."
)

def build_cross_client_agent(
    t3_tools: list | None = None,
    model: str = "gemini-2.5-flash",
) -> Agent:
    tools = get_cross_client_tools()
    if t3_tools:
        tools.extend(t3_tools)
    return Agent(
        name="device_agent",
        model=model,
        instruction=CROSS_CLIENT_INSTRUCTION,
        tools=tools,
    )
```

- [x] Create `backend/app/agents/cross_client_agent.py`
- [x] Remove cross-client tools from persona agents (no longer in `_default_tools_for_persona`)

---

### Step 7: Wire TaskArchitect into Root Agent
**File:** `backend/app/agents/root_agent.py`
**What:** TaskArchitect becomes a tool the root agent can invoke for complex multi-step tasks. Use ADK `AgentTool` pattern.

From ADK docs — AgentTool wraps an agent as a tool:
```python
from google.adk.tools import AgentTool
tools = [AgentTool(agent=task_architect_agent)]
```

But since TaskArchitect has its own analyze+build flow, we wrap it as a FunctionTool:
```python
async def plan_complex_task(task_description: str) -> dict:
    """Decompose a complex multi-step task into a pipeline of sub-agents.
    Use this when the user request requires multiple steps, different skills,
    or coordination between personas."""
    architect = TaskArchitect(user_id="__pending__")
    blueprint = await architect.analyse_task(task_description)
    # Return the plan for now — execution handled separately
    return blueprint.to_dict()
```

- [x] Create `plan_complex_task` FunctionTool in root_agent.py or as dedicated tool
- [x] Add it to root agent's tools (root gets ONE tool: plan_complex_task)
- [x] Update ROOT_INSTRUCTION to describe when to use complex task planning

---

### Step 8: Rewrite `build_root_agent()` with 3-Layer Routing
**File:** `backend/app/agents/root_agent.py`
**What:** Root agent now has 3 routing paths via sub_agents: persona pool, task_architect, device_agent.

```python
ROOT_INSTRUCTION = (
    "You are Omni, a multi-persona AI hub...\n\n"
    "You classify every request into one of three paths:\n\n"
    "1. **Simple Task** → transfer to the best persona agent:\n"
    "   {persona_list}\n\n"
    "2. **Complex Task** (multi-step, requires coordination) → transfer to task_planner\n"
    "   Examples: 'Build a dashboard', 'Research X then write a blog post'\n\n"
    "3. **Device Action** (involves connected client/device) → transfer to device_agent\n"
    "   Examples: 'Take a screenshot on desktop', 'Open a tab in Chrome'\n\n"
    "Rules:\n"
    "- NEVER answer directly. Always transfer.\n"
    "- If the user names a persona, transfer to that persona.\n"
    "- For multi-step tasks that need coordination, use task_planner.\n"
    "- For device/client actions, use device_agent."
)
```

```python
def build_root_agent(
    personas: list[PersonaResponse] | None = None,
    tools_by_persona: dict[str, list] | None = None,
    model: str | None = None,
) -> Agent:
    effective_model = model or LIVE_MODEL

    # Layer 1: Persona agents with capability-matched tools
    persona_agents = []
    for p in personas:
        persona_tools = tools_by_persona.get(p.id, []) if tools_by_persona else []
        persona_agents.append(create_agent(p, persona_tools, model=effective_model))

    # Layer 2: Task planner (no direct tools — uses TaskArchitect)
    task_planner = build_task_planner_agent(model=effective_model)

    # Layer 3: Cross-client orchestrator
    t3_tools = tools_by_persona.get("__device__", []) if tools_by_persona else []
    device_agent = build_cross_client_agent(t3_tools, model=effective_model)

    sub_agents = persona_agents + [task_planner, device_agent]

    # Build dynamic persona list for instruction
    persona_list = "\n".join(
        f"   - {p.id} — {p.name}: {p.system_instruction[:60]}..."
        for p in personas
    )

    root = Agent(
        name="omni_root",
        model=effective_model,
        instruction=ROOT_INSTRUCTION.format(persona_list=persona_list),
        sub_agents=sub_agents,
    )
    return root
```

- [x] Rewrite `build_root_agent()` to accept `tools_by_persona` dict
- [x] Build persona agents with per-persona tool lists
- [x] Build task_planner sub-agent
- [x] Build device_agent sub-agent
- [x] Update ROOT_INSTRUCTION to be dynamic with persona list
- [x] Update callers of `build_root_agent()` (WS handler / session setup)

---

### Step 9: Update Agent Factory — Capability-Based Tool Assignment
**File:** `backend/app/agents/agent_factory.py`
**What:** `create_agent()` now receives pre-filtered tools. No more `_default_tools_for_persona()` with hardcoded sets.

```python
def create_agent(
    persona: PersonaResponse,
    extra_tools: list | None = None,
    model: str | None = None,
) -> Agent:
    # T1 tools matched by persona capabilities
    tools = get_tools_for_capabilities(persona.capabilities)
    # T2 tools (pre-filtered by caller using tag matching)
    if extra_tools:
        tools.extend(extra_tools)
    # NO cross-client tools here — those go to device_agent
    ...
```

- [x] Remove cross_client import from create_agent
- [x] Use `get_tools_for_capabilities(persona.capabilities)` for T1
- [x] Cross-client tools no longer added to every persona

---

### Step 10: Update Session Bootstrap (WS Handler)
**File:** Wherever `build_root_agent` is called (likely WS handler or session service)
**What:** Wire up the new tool registry flow.

```python
# Before (old):
tools = await tool_registry.build_for_session(user_id)
root = build_root_agent(personas, mcp_tools=tools)

# After (new):
tools_by_persona = await tool_registry.build_for_session(user_id, personas)
root = build_root_agent(personas, tools_by_persona=tools_by_persona)
```

- [x] Find and update all callers of `build_root_agent`
- [x] Pass `tools_by_persona` dict instead of flat tool list

---

## Execution Order

1. **Step 1** — `ToolCapability` enum + `tags` on PluginManifest (no breaking changes)
2. **Step 2** — `capabilities` on persona models (backward compatible with default `[]`)
3. **Step 3** — Tag T1 tools, refactor agent_factory
4. **Step 4** — Tag all T2 plugins
5. **Step 5** — Refactor ToolRegistry for per-persona matching
6. **Step 6** — Create cross-client orchestrator agent
7. **Step 7** — Wire TaskArchitect as routing option
8. **Step 8** — Rewrite root_agent.py with 3-layer routing
9. **Step 9** — Update agent_factory to capability-based
10. **Step 10** — Update session bootstrap callers
11. **Step 11** *(added)* — OAuth MCP support (`MCP_OAUTH` kind, `OAuthService`, 3 API endpoints, UI popup flow)
12. **Step 12** *(added)* — Smart session features: session title auto-generation, cross-client session suggestion broadcast, live client activity dots, voice persona switcher UI — see **Smart Session & Cross-Client Improvements** below

---

## Smart Session & Cross-Client Improvements

### Session Title Auto-Generation
- **Backend** (`backend/app/services/session_service.py`): `generate_title_from_message(session_id, user_message)` — checks if session still has the default `"Session 202…"` title, then calls `_generate_title()` which sends a Gemini `TEXT_MODEL` request (via `asyncio.to_thread`) to produce a ≤6 word title; updates Firestore non-blocking.
- **Trigger points**: first user text message in both `/ws/live` (`_upstream`) and `/ws/chat` handler.
- **Frontend** (`dashboard/src/hooks/useChatWebSocket.js`): after the first `sendText()` call, schedules `loadSessions()` refresh after 4 s so the auto-generated title appears in the sidebar.

### Cross-Client Session Suggestion
- **EventBus broadcast** (`ws_live.py`): after a client connects and auth succeeds, publishes `session_suggestion` to `EventBus` with `available_clients: [str(client_type)]` and a human-readable message. The `_relay_cross_events` helper skips `session_suggestion` and `client_status_update` so `/ws/events` remains the sole delivery channel for infrastructure events (prevents triple-delivery).
- **Dashboard** (`useEventSocket.js`): routes `session_suggestion` → `sessionSuggestionStore.setSuggestion()` + `sessionStore.ensureSession()` + `sessionStore.setActiveSession()` (in that order to avoid orphaned active IDs).
- **Desktop client** (`desktop-client/src/ws_client.py`): `_dispatch()` handles `session_suggestion` and invokes registered handler callback.
- **Chrome extension** (`chrome-extension/background.js`): `handleServerMessage()` forwards `session_suggestion` to popup; `popup.js` renders a dismissible blue banner.

### Live Client Activity Dots (Sidebar)
- `Sidebar.jsx` subscribes to `useClientStore` and renders up to 3 green dots (+ overflow count) next to the **Clients** nav item, reflecting currently connected clients in real-time.

### Voice Persona Switcher
- `DashboardPage.jsx` overview panel: dropdown `<select>` listing all personas (`name — voice`), wired to `personaStore.setActivePersona()`. A `useEffect` watching `activePersona?.id` triggers `voice.reconnect()` when the persona changes, so the backend resumes with the new voice/system instruction.



## ADK Reference Patterns Used

### Transfer Between Sub-Agents (ADK built-in)
```python
root = Agent(name="root", sub_agents=[agent_a, agent_b])
# Root uses transfer_to_agent("agent_a") automatically
```

### AgentTool (ADK — Agent as a Tool)
```python
from google.adk.tools import AgentTool
tools = [AgentTool(agent=helper_agent, skip_summarization=True)]
```

### Workflow Agents (ADK)
```python
from google.adk.agents import SequentialAgent, ParallelAgent, LoopAgent
stage = ParallelAgent(name="research", sub_agents=[sage, nova])
pipeline = SequentialAgent(name="pipeline", sub_agents=[stage, dev])
```

### LongRunningFunctionTool (ADK)
```python
from google.adk.tools import LongRunningFunctionTool
long_tool = LongRunningFunctionTool(func=start_build_job)
```

### Streaming Tools (ADK — Experimental, Live API only)
```python
async def monitor_output(sandbox_id: str) -> AsyncGenerator[str, None]:
    while True:
        output = await poll_sandbox(sandbox_id)
        if output: yield output
        await asyncio.sleep(1)
```
