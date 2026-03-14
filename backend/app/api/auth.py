"""Auth endpoints — token verification, current user info, account deletion."""

from fastapi import APIRouter

from app.middleware.auth_middleware import AuthenticatedUser, CurrentUser
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/verify")
async def verify_token(user: CurrentUser) -> dict:
    """Verify a Firebase ID token and return the user profile.

    The token is passed via `Authorization: Bearer <token>` header.
    If valid, returns user info; otherwise 401.
    """
    return _user_response(user)


@router.get("/me")
async def get_me(user: CurrentUser) -> dict:
    """Return the currently authenticated user's profile."""
    return _user_response(user)


@router.delete("/account")
async def delete_account(user: CurrentUser) -> dict:
    """Permanently delete the user's account and ALL associated data.

    Deletes from:
    - Firestore: sessions, personas, memories/{uid}/facts
    - Vertex AI: Agent Engine memories (if enabled)
    - Firebase Auth: the user record itself
    """
    uid = user.uid
    deleted: dict[str, int | str] = {}

    # 1. Delete all Firestore sessions for this user
    try:
        from app.services.session_service import get_session_service

        svc = get_session_service()
        sessions = await svc.list_sessions(uid)
        for s in sessions:
            await svc.delete_session(uid, s.id)
        deleted["sessions"] = len(sessions)
    except Exception:
        logger.warning("account_delete_sessions_failed", user_id=uid, exc_info=True)
        deleted["sessions"] = "error"

    # 2. Delete all user-created personas
    try:
        from app.agents.personas import get_default_persona_ids
        from app.services.persona_service import get_persona_service

        svc = get_persona_service()
        personas = await svc.list_personas(uid)
        default_ids = get_default_persona_ids()
        count = 0
        for p in personas:
            if p.id not in default_ids:
                await svc.delete_persona(uid, p.id)
                count += 1
        deleted["personas"] = count
    except Exception:
        logger.warning("account_delete_personas_failed", user_id=uid, exc_info=True)
        deleted["personas"] = "error"

    # 3. Delete all Firestore memories (subcollection)
    try:
        from app.services.memory_service import get_memory_service

        mem_svc = get_memory_service()
        cleared = await mem_svc.clear_facts(uid)
        deleted["memories"] = cleared
    except Exception:
        logger.warning("account_delete_memories_failed", user_id=uid, exc_info=True)
        deleted["memories"] = "error"

    # 4. Purge Vertex AI Agent Engine memories (if enabled)
    try:
        from app.services.agent_engine_service import get_agent_engine_service

        ae = get_agent_engine_service()
        if ae.enabled:
            purged = await ae.purge_user_memories(user_id=uid)
            deleted["vertex_memories"] = purged
        else:
            deleted["vertex_memories"] = "disabled"
    except Exception:
        logger.warning("account_delete_vertex_memories_failed", user_id=uid, exc_info=True)
        deleted["vertex_memories"] = "error"

    # 5. Delete Firebase Auth user
    try:
        from app.middleware.auth_middleware import _get_firebase_app

        _get_firebase_app()
        from firebase_admin import auth as firebase_auth

        firebase_auth.delete_user(uid)
        deleted["firebase_auth"] = "deleted"
    except Exception:
        logger.warning("account_delete_firebase_auth_failed", user_id=uid, exc_info=True)
        deleted["firebase_auth"] = "error"

    # 6. Disconnect any active WebSocket connections
    try:
        from app.services.connection_manager import get_connection_manager

        mgr = get_connection_manager()
        clients = mgr.get_connected_clients(uid)
        for c in clients:
            await mgr.disconnect(uid, c.client_type)
        deleted["connections_closed"] = len(clients)
    except Exception:
        logger.warning("account_delete_connections_failed", user_id=uid, exc_info=True)

    logger.info("account_deleted", user_id=uid, summary=deleted)
    return {"status": "deleted", "user_id": uid, "details": deleted}


def _user_response(user: AuthenticatedUser) -> dict:
    return {
        "user_id": user.uid,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
    }
