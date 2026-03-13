"""WebSocket message schemas — single source of truth for WS protocol.

Client ↔ Server message contracts. Frontend mocks these during development.
Binary frames (audio) are NOT represented here — they bypass JSON parsing.

Discriminated union ``WSMessage`` lets callers parse any JSON frame into the
correct Pydantic model automatically via ``WSMessage.model_validate_json(raw)``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ── Enums ─────────────────────────────────────────────────────────────


class AgentState(StrEnum):
    """Server-side agent status."""

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


class ContentType(StrEnum):
    """Payload kind inside an ``AgentResponse``."""

    TEXT = "text"
    AUDIO = "audio"
    GENUI = "genui"
    TRANSCRIPTION = "transcription"


class TranscriptionDirection(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class ToolStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionKind(StrEnum):
    """Classifies the source/type of a tool action for UI display."""

    TOOL = "tool"  # Built-in ADK tool
    MCP = "mcp"  # MCP server tool
    NATIVE_PLUGIN = "native_plugin"  # Native plugin (e.g. Google Calendar)
    CROSS_DEVICE = "cross_device"  # T3 reverse-RPC to another client
    AGENT_TRANSFER = "agent_transfer"  # Sub-agent routing
    IMAGE_GEN = "image_gen"  # Image generation tool


# ── Client → Server ──────────────────────────────────────────────────


class AuthMessage(BaseModel):
    """First message the client must send after WS connect."""

    type: Literal["auth"] = "auth"
    token: str
    client_type: str = "web"
    capabilities: list[str] = []
    local_tools: list[dict] = []


class TextMessage(BaseModel):
    type: Literal["text"] = "text"
    content: str


class ImageMessage(BaseModel):
    type: Literal["image"] = "image"
    data_base64: str
    mime_type: str = "image/jpeg"


class PersonaSwitchMessage(BaseModel):
    type: Literal["persona_switch"] = "persona_switch"
    persona_id: str


class MCPToggleMessage(BaseModel):
    type: Literal["mcp_toggle"] = "mcp_toggle"
    mcp_id: str
    enabled: bool


class SessionSuggestionMessage(BaseModel):
    """Server suggests user to switch to another device for uninterrupted session."""
    type: Literal["session_suggestion"] = "session_suggestion"
    available_clients: list[str]  # e.g., ["desktop", "mobile"]
    message: str


class JoinSessionMessage(BaseModel):
    """Client responds to session suggestion - join other session or continue new."""
    type: Literal["join_session"] = "join_session"
    join: bool  # True = join existing, False = start new


class ControlMessage(BaseModel):
    """Generic control envelope (start/stop voice, etc.)."""

    type: Literal["control"] = "control"
    action: str
    payload: dict | None = None


# ── Server → Client ──────────────────────────────────────────────────


class AuthResponse(BaseModel):
    type: Literal["auth_response"] = "auth_response"
    status: str  # "ok" | "error"
    user_id: str = ""
    session_id: str = ""  # ADK session ID
    firestore_session_id: str = ""  # Firestore session ID (for URL routing)
    available_tools: list[str] = []  # Tool names available for this session
    other_clients_online: list[str] = []  # Other connected client types
    error: str = ""


class AgentResponse(BaseModel):
    """Text / GenUI payload from the agent."""

    type: Literal["response"] = "response"
    content_type: ContentType = ContentType.TEXT
    data: str = ""
    genui: dict | None = None


class TranscriptionMessage(BaseModel):
    type: Literal["transcription"] = "transcription"
    direction: TranscriptionDirection
    text: str
    finished: bool = False


class ToolCallMessage(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    tool_name: str
    arguments: dict = {}
    status: ToolStatus = ToolStatus.STARTED
    action_kind: ActionKind = ActionKind.TOOL
    source_label: str = ""  # Human-readable source (e.g. MCP server name, plugin name, device)


class ToolResponseMessage(BaseModel):
    type: Literal["tool_response"] = "tool_response"
    tool_name: str
    result: str = ""
    success: bool = True
    action_kind: ActionKind = ActionKind.TOOL
    source_label: str = ""


class ImageResponseMessage(BaseModel):
    """Server → client: an image produced by an image generation tool.

    For ``generate_image``: single image via ``image_base64``.
    For ``generate_rich_image`` (Gemini interleaved): ordered ``parts``
    list preserving the text↔image interleaving so the dashboard can
    render an illustrated guide exactly as Gemini produced it.
    """

    type: Literal["image_response"] = "image_response"
    tool_name: str = "generate_image"
    # Single image (generate_image)
    image_base64: str = ""
    mime_type: str = "image/png"
    image_url: str = ""
    description: str = ""
    # Multi-image (generate_rich_image / Gemini interleaved)
    images: list[dict] = []
    text: str = ""
    # Interleaved parts in display order (generate_rich_image)
    # Each item: {"type": "text", "content": "..."} or
    #            {"type": "image", "base64": "...", "mime_type": "..."}
    parts: list[dict] = []


class AgentActivityMessage(BaseModel):
    """Real-time agent activity: sub-agent calls, reasoning, MCP invocations.

    This provides transparency into what the async agent is doing behind the scenes.
    """
    type: Literal["agent_activity"] = "agent_activity"
    activity_type: str  # "sub_agent_call", "reasoning", "mcp_call", "tool_call", "waiting"
    title: str  # Short description
    details: str = ""  # More info
    status: str = "started"  # started, in_progress, completed, failed
    timestamp: str = ""  # ISO timestamp
    parent_agent: str = ""  # Which agent is doing this
    progress: float = 0.0  # 0.0 to 1.0 for progress indication


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    code: str
    description: str = ""


class AgentTransferMessage(BaseModel):
    """Notification that the root agent routed to a sub-agent."""

    type: Literal["agent_transfer"] = "agent_transfer"
    from_agent: str = ""
    to_agent: str = ""
    message: str = ""


class StatusMessage(BaseModel):
    type: Literal["status"] = "status"
    state: AgentState = AgentState.IDLE
    detail: str = ""


class PersonaChangedMessage(BaseModel):
    type: Literal["persona_changed"] = "persona_changed"
    persona_id: str
    persona_name: str = ""
    voice: str = ""


class ConnectedMessage(BaseModel):
    type: Literal["connected"] = "connected"
    session_id: str
    resumed_from: str = ""


class CrossClientMessage(BaseModel):
    type: Literal["cross_client"] = "cross_client"
    action: str
    target: str = ""
    data: dict = {}


class ClientStatusUpdateMessage(BaseModel):
    type: Literal["client_status_update"] = "client_status_update"
    clients: list[dict] = []
    event: str = ""  # "connected" or "disconnected"
    client_type: str = ""


# ── T3 Reverse-RPC Messages ─────────────────────────────────────────


class CapabilityUpdateMessage(BaseModel):
    """Client updates its capabilities mid-session."""

    type: Literal["capability_update"] = "capability_update"
    added: list[str] = []
    removed: list[str] = []
    added_tools: list[dict] = []  # New local_tools to register
    removed_tools: list[str] = []  # Tool names to unregister


class ToolInvocationMessage(BaseModel):
    """Server → client: invoke a T3 local tool on the client."""

    type: Literal["tool_invocation"] = "tool_invocation"
    call_id: str
    tool: str
    args: dict = {}


class ToolResultMessage(BaseModel):
    """Client → server: result of a T3 local tool invocation."""

    type: Literal["tool_result"] = "tool_result"
    call_id: str
    result: dict | str = {}
    error: str = ""


# ── Discriminated Union ──────────────────────────────────────────────

ClientMessage = Annotated[
    AuthMessage | TextMessage | ImageMessage | PersonaSwitchMessage | MCPToggleMessage | ControlMessage | CapabilityUpdateMessage | ToolResultMessage,
    Field(discriminator="type"),
]
"""Any JSON frame the **client** may send (excluding binary audio)."""

ServerMessage = Annotated[
    AuthResponse | AgentResponse | TranscriptionMessage | ToolCallMessage | ToolResponseMessage | ImageResponseMessage | ErrorMessage | StatusMessage | PersonaChangedMessage | ConnectedMessage | CrossClientMessage | ClientStatusUpdateMessage | ToolInvocationMessage,
    Field(discriminator="type"),
]
"""Any JSON frame the **server** may send (excluding binary audio)."""

WSMessage = Annotated[
    AuthMessage | TextMessage | ImageMessage | PersonaSwitchMessage | MCPToggleMessage | ControlMessage | CapabilityUpdateMessage | ToolResultMessage | AuthResponse | AgentResponse | TranscriptionMessage | ToolCallMessage | ToolResponseMessage | ImageResponseMessage | ErrorMessage | StatusMessage | PersonaChangedMessage | ConnectedMessage | CrossClientMessage | ClientStatusUpdateMessage | ToolInvocationMessage,
    Field(discriminator="type"),
]
"""Parse any WS JSON frame: ``TypeAdapter(WSMessage).validate_json(raw)``."""
