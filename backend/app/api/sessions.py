"""CRUD /sessions — session history management."""

from fastapi import APIRouter, Depends

from app.middleware.auth_middleware import CurrentUser
from app.models.session import (
    SessionCreate,
    SessionListItem,
    SessionResponse,
    SessionUpdate,
)
from app.services.session_service import SessionService, get_session_service

router = APIRouter()


@router.post("/", status_code=201)
async def create_session(
    body: SessionCreate,
    user: CurrentUser,
    svc: SessionService = Depends(get_session_service),  # noqa: B008
) -> SessionResponse:
    """Create a new conversation session."""
    return await svc.create_session(user.uid, body)


@router.get("/")
async def list_sessions(
    user: CurrentUser,
    svc: SessionService = Depends(get_session_service),  # noqa: B008
) -> list[SessionListItem]:
    """List all sessions for the current user (newest first)."""
    return await svc.list_sessions(user.uid)


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    user: CurrentUser,
    svc: SessionService = Depends(get_session_service),  # noqa: B008
) -> SessionResponse:
    """Get a single session by ID."""
    return await svc.get_session(user.uid, session_id)


@router.put("/{session_id}")
async def update_session(
    session_id: str,
    body: SessionUpdate,
    user: CurrentUser,
    svc: SessionService = Depends(get_session_service),  # noqa: B008
) -> SessionResponse:
    """Update session metadata (title, persona, message count)."""
    return await svc.update_session(user.uid, session_id, body)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user: CurrentUser,
    svc: SessionService = Depends(get_session_service),  # noqa: B008
) -> None:
    """Delete a session (user-scoped)."""
    await svc.delete_session(user.uid, session_id)
