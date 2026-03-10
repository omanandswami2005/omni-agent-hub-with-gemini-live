"""Session Pydantic schemas."""

from datetime import datetime

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
    created_at: datetime
    updated_at: datetime


class SessionListItem(BaseModel):
    """Compact session for list views."""

    id: str
    persona_id: str
    title: str = ""
    message_count: int = 0
    created_at: datetime
    updated_at: datetime
