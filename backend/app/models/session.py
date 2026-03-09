"""Session Pydantic schemas."""

from pydantic import BaseModel


class SessionInfo(BaseModel):
    id: str
    user_id: str
    persona_id: str
    created_at: str
    last_active: str
    message_count: int = 0


class SessionList(BaseModel):
    sessions: list[SessionInfo] = []
