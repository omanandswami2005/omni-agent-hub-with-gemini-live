"""Persona management — Firestore-backed CRUD + built-in defaults.

Firestore collection layout:
  personas/{persona_id}  →  { user_id, name, voice, system_instruction,
                               mcp_ids, avatar_url, is_default, created_at }

``list_personas`` merges the five built-in defaults with any user-created
personas so the frontend always sees a complete set.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from google.cloud import firestore

from app.agents.personas import get_default_persona_ids, get_default_personas
from app.config import settings
from app.models.persona import PersonaCreate, PersonaResponse, PersonaUpdate
from app.utils.errors import AuthorizationError, NotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)

COLLECTION = "personas"


class PersonaService:
    """Firestore-backed persona CRUD, scoped per user."""

    def __init__(self, db: firestore.Client | None = None) -> None:
        self._db = db

    @property
    def db(self) -> firestore.Client:
        if self._db is None:
            self._db = firestore.Client(project=settings.GOOGLE_CLOUD_PROJECT or None)
        return self._db

    # ── List ──────────────────────────────────────────────────────────

    async def list_personas(self, user_id: str) -> list[PersonaResponse]:
        """Return defaults + user-created personas."""
        defaults = get_default_personas()
        query = (
            self.db.collection(COLLECTION)
            .where(filter=firestore.FieldFilter("user_id", "==", user_id))
        )
        user_personas = [
            PersonaResponse(id=snap.id, **snap.to_dict())
            for snap in query.stream()
        ]
        user_personas.sort(key=lambda p: p.created_at or datetime.min, reverse=True)
        return defaults + user_personas

    # ── Get one ───────────────────────────────────────────────────────

    async def get_persona(self, user_id: str, persona_id: str) -> PersonaResponse:
        """Fetch a single persona by ID (default or user-owned)."""
        # Check defaults first
        for p in get_default_personas():
            if p.id == persona_id:
                return p

        snap = self.db.collection(COLLECTION).document(persona_id).get()
        if not snap.exists:
            raise NotFoundError("Persona", persona_id)
        doc = snap.to_dict()
        if doc["user_id"] != user_id:
            raise NotFoundError("Persona", persona_id)
        return PersonaResponse(id=snap.id, **doc)

    # ── Create ────────────────────────────────────────────────────────

    async def create_persona(
        self, user_id: str, data: PersonaCreate
    ) -> PersonaResponse:
        now = datetime.now(UTC)
        persona_id = uuid4().hex
        doc = {
            "user_id": user_id,
            "name": data.name,
            "voice": data.voice,
            "system_instruction": data.system_instruction,
            "mcp_ids": data.mcp_ids,
            "avatar_url": data.avatar_url,
            "is_default": False,
            "created_at": now,
        }
        self.db.collection(COLLECTION).document(persona_id).set(doc)
        logger.info("persona_created", persona_id=persona_id, user_id=user_id)
        return PersonaResponse(id=persona_id, **doc)

    # ── Update ────────────────────────────────────────────────────────

    async def update_persona(
        self, user_id: str, persona_id: str, data: PersonaUpdate
    ) -> PersonaResponse:
        if persona_id in get_default_persona_ids():
            raise AuthorizationError("Cannot modify built-in personas")

        # Verify ownership
        await self.get_persona(user_id, persona_id)

        updates = {k: v for k, v in data.model_dump(exclude_none=True).items()}
        if not updates:
            return await self.get_persona(user_id, persona_id)

        self.db.collection(COLLECTION).document(persona_id).update(updates)
        logger.info("persona_updated", persona_id=persona_id)
        return await self.get_persona(user_id, persona_id)

    # ── Delete ────────────────────────────────────────────────────────

    async def delete_persona(self, user_id: str, persona_id: str) -> None:
        if persona_id in get_default_persona_ids():
            raise AuthorizationError("Cannot delete built-in personas")

        # Verify ownership
        await self.get_persona(user_id, persona_id)
        self.db.collection(COLLECTION).document(persona_id).delete()
        logger.info("persona_deleted", persona_id=persona_id, user_id=user_id)


# ── Module-level singleton ────────────────────────────────────────────

_persona_service: PersonaService | None = None


def get_persona_service() -> PersonaService:
    global _persona_service
    if _persona_service is None:
        _persona_service = PersonaService()
    return _persona_service
