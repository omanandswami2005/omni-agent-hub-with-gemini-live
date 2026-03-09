"""Persona Pydantic schemas."""

from pydantic import BaseModel


class PersonaCreate(BaseModel):
    name: str
    voice: str  # Gemini voice: Charon, Kore, Aoede, Fenrir, Leda, etc.
    instructions: str
    tools: list[str] = []  # Tool names to enable
    icon: str = ""


class PersonaResponse(PersonaCreate):
    id: str
    user_id: str
    is_default: bool = False
