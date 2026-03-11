"""Session management — Firestore-backed CRUD.

All sessions are scoped to a user_id. Firestore collection layout:
  sessions/{session_id}  →  { user_id, persona_id, title, message_count, created_at, updated_at }

Indexed on (user_id, created_at DESC) for efficient list queries.
"""

from datetime import UTC, datetime
from uuid import uuid4

from google.cloud import firestore

from app.config import settings
from app.models.session import (
    SessionCreate,
    SessionListItem,
    SessionResponse,
    SessionUpdate,
)
from app.utils.errors import NotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)

COLLECTION = "sessions"


class SessionService:
    """Firestore-backed session CRUD, scoped per user."""

    def __init__(self, db: firestore.Client | None = None) -> None:
        self._db = db

    @property
    def db(self) -> firestore.Client:
        if self._db is None:
            self._db = firestore.Client(project=settings.GOOGLE_CLOUD_PROJECT or None)
        return self._db

    # ── Create ────────────────────────────────────────────────────────

    async def create_session(self, user_id: str, data: SessionCreate) -> SessionResponse:
        now = datetime.now(UTC)
        session_id = uuid4().hex
        doc = {
            "user_id": user_id,
            "persona_id": data.persona_id,
            "title": data.title or f"Session {now:%Y-%m-%d %H:%M}",
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self.db.collection(COLLECTION).document(session_id).set(doc)
        logger.info("session_created", session_id=session_id, user_id=user_id)
        return SessionResponse(id=session_id, **doc)

    # ── Read one ──────────────────────────────────────────────────────

    async def get_session(self, user_id: str, session_id: str) -> SessionResponse:
        snap = self.db.collection(COLLECTION).document(session_id).get()
        if not snap.exists:
            raise NotFoundError("Session", session_id)
        doc = snap.to_dict()
        if doc["user_id"] != user_id:
            raise NotFoundError("Session", session_id)
        return SessionResponse(id=snap.id, **doc)

    # ── List ──────────────────────────────────────────────────────────

    async def list_sessions(self, user_id: str) -> list[SessionListItem]:
        query = (
            self.db.collection(COLLECTION)
            .where("user_id", "==", user_id)
        )
        items = [
            SessionListItem(id=snap.id, **snap.to_dict())
            for snap in query.stream()
        ]
        items.sort(key=lambda s: s.created_at, reverse=True)
        return items

    # ── Update ────────────────────────────────────────────────────────

    async def update_session(
        self, user_id: str, session_id: str, data: SessionUpdate
    ) -> SessionResponse:
        # Verify ownership
        await self.get_session(user_id, session_id)

        updates = {k: v for k, v in data.model_dump(exclude_none=True).items()}
        updates["updated_at"] = datetime.now(UTC)

        self.db.collection(COLLECTION).document(session_id).update(updates)
        logger.info("session_updated", session_id=session_id)
        return await self.get_session(user_id, session_id)

    # ── Delete ────────────────────────────────────────────────────────

    async def delete_session(self, user_id: str, session_id: str) -> None:
        # Verify ownership
        await self.get_session(user_id, session_id)
        self.db.collection(COLLECTION).document(session_id).delete()
        logger.info("session_deleted", session_id=session_id, user_id=user_id)


# ── Module-level singleton ────────────────────────────────────────────

_session_service: SessionService | None = None


def get_session_service() -> SessionService:
    global _session_service
    if _session_service is None:
        _session_service = SessionService()
    return _session_service
