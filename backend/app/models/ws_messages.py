"""WebSocket message schemas — single source of truth for WS protocol.

Client ↔ Server message contracts. Frontend mocks these during development.
Binary frames (audio) are NOT represented here — they bypass JSON parsing.
"""

from pydantic import BaseModel


# === Client → Server ===

class AuthMessage(BaseModel):
    type: str = "auth"
    token: str


class TextMessage(BaseModel):
    type: str = "text"
    content: str


class ImageMessage(BaseModel):
    type: str = "image"
    data: str  # base64 JPEG
    mime_type: str = "image/jpeg"


class ControlMessage(BaseModel):
    type: str = "control"
    action: str  # switch_persona, start_voice, stop_voice
    persona_id: str = ""


# === Server → Client ===

class ResponseMessage(BaseModel):
    type: str = "response"
    content: str
    genui: dict | None = None  # Optional GenUI component data


class TranscriptionMessage(BaseModel):
    type: str = "transcription"
    direction: str  # "input" | "output"
    text: str
    finished: bool


class StatusMessage(BaseModel):
    type: str = "status"
    state: str  # idle, listening, processing, speaking, error
    detail: str = ""


class ToolMessage(BaseModel):
    type: str  # "tool_start" | "tool_end"
    tool: str
    success: bool = True


class CrossClientMessage(BaseModel):
    type: str = "cross_client"
    action: str
    target: str  # "web" | "desktop" | "chrome_ext" | "all"
    data: dict = {}


class ErrorMessage(BaseModel):
    type: str = "error"
    code: str
    message: str
