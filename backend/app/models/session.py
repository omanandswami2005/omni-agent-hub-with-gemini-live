"""Session Pydantic schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

# ── Request schemas ───────────────────────────────────────────────────


class SessionCreate(BaseModel):
    """Body for POST /sessions."""

    persona_id: str = "assistant"
    title: str = ""


class SessionUpdate(BaseModel):
    """Body for PUT /sessions/{id}."""

    title: str | None = None
    persona_id: str | None = None
    message_count: int | None = None


# ── Response schemas ──────────────────────────────────────────────────


class SessionResponse(BaseModel):
    """Full session object returned by API."""

    id: str
    user_id: str
    persona_id: str
    title: str = ""
    message_count: int = 0
    adk_session_id: str = ""
    created_at: datetime
    updated_at: datetime


class SessionListItem(BaseModel):
    """Compact session for list views."""

    id: str
    persona_id: str
    title: str = ""
    message_count: int = 0
    adk_session_id: str = ""
    created_at: datetime
    updated_at: datetime


# ── Chat message schema (for API responses, not stored in Firestore) ───


class ChatMessage(BaseModel):
    """A chat message extracted from ADK session events."""

    role: str  # 'user' | 'assistant' | 'system'
    content: str = ""
    type: str = "text"  # 'text' | 'tool_call' | 'tool_response' | 'image' | 'action'
    source: str = "text"  # 'text' | 'voice'
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    action_kind: str = ""
    source_label: str = ""
    success: bool | None = None
    result: str = ""
    responded: bool = False
    image_url: str = ""
    description: str = ""
