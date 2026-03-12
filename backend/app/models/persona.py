"""Persona Pydantic schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PersonaCreate(BaseModel):
    """Body for POST /personas."""

    name: str
    voice: str = "Kore"  # Gemini voice: Charon, Kore, Aoede, Fenrir, Leda, …
    system_instruction: str = ""
    mcp_ids: list[str] = []
    avatar_url: str = ""
    capabilities: list[str] = []  # ToolCapability tags this persona needs


class PersonaUpdate(BaseModel):
    """Body for PUT /personas/{id}. All fields optional."""

    name: str | None = None
    voice: str | None = None
    system_instruction: str | None = None
    mcp_ids: list[str] | None = None
    avatar_url: str | None = None
    capabilities: list[str] | None = None


class PersonaResponse(BaseModel):
    """Full persona returned by the API."""

    id: str
    user_id: str
    name: str
    voice: str = "Kore"
    system_instruction: str = ""
    mcp_ids: list[str] = []
    avatar_url: str = ""
    is_default: bool = False
    created_at: Optional[datetime] = None
    capabilities: list[str] = []
