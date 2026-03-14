"""GET /init — Single bootstrap endpoint that returns all data the frontend
needs on first load in one round-trip, eliminating waterfall latency from
multiple sequential API calls.
"""

import asyncio

from fastapi import APIRouter, Depends

from app.middleware.auth_middleware import CurrentUser
from app.services.mcp_manager import get_mcp_manager
from app.services.persona_service import PersonaService, get_persona_service
from app.services.plugin_registry import get_plugin_registry
from app.services.session_service import SessionService, get_session_service
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/init")
async def bootstrap(
    user: CurrentUser,
    persona_svc: PersonaService = Depends(get_persona_service),  # noqa: B008
    session_svc: SessionService = Depends(get_session_service),  # noqa: B008
) -> dict:
    """Return sessions, personas, and MCP catalog in one response.

    Firestore calls (sessions, personas) are async and run concurrently.
    MCP catalog/enabled are sync (in-memory) — called after the gather.
    """
    mcp_mgr = get_mcp_manager()
    plugin_registry = get_plugin_registry()

    # Run the async Firestore calls concurrently (with timeout to prevent
    # frontend hanging if Firestore is slow at a conference venue).
    _INIT_TIMEOUT = 10  # seconds
    try:
        sessions_result, personas_result = await asyncio.wait_for(
            asyncio.gather(
                session_svc.list_sessions(user.uid),
                persona_svc.list_personas(user.uid),
                return_exceptions=True,
            ),
            timeout=_INIT_TIMEOUT,
        )
    except TimeoutError:
        logger.warning("init_firestore_timeout", user_id=user.uid, timeout=_INIT_TIMEOUT)
        sessions_result, personas_result = [], []

    # Gracefully handle partial failures — return what succeeded
    if isinstance(sessions_result, BaseException):
        logger.warning("init_sessions_failed", user_id=user.uid, exc_info=sessions_result)
        sessions_result = []
    if isinstance(personas_result, BaseException):
        logger.warning("init_personas_failed", user_id=user.uid, exc_info=personas_result)
        personas_result = []

    # MCP catalog/enabled are sync in-memory lookups — no latency
    try:
        mcp_catalog = mcp_mgr.get_catalog(user_id=user.uid)
    except Exception:
        logger.warning("init_mcp_catalog_failed", user_id=user.uid, exc_info=True)
        mcp_catalog = []
    try:
        mcp_enabled = mcp_mgr.get_enabled_ids(user.uid)
    except Exception:
        logger.warning("init_mcp_enabled_failed", user_id=user.uid, exc_info=True)
        mcp_enabled = []

    # Plugin catalog (new unified system)
    try:
        plugin_catalog = plugin_registry.get_catalog(user_id=user.uid)
    except Exception:
        logger.warning("init_plugin_catalog_failed", user_id=user.uid, exc_info=True)
        plugin_catalog = []

    return {
        "sessions": [s.model_dump() if hasattr(s, "model_dump") else s for s in sessions_result],
        "personas": [p.model_dump() if hasattr(p, "model_dump") else p for p in personas_result],
        "mcp_catalog": [m.model_dump() if hasattr(m, "model_dump") else m for m in mcp_catalog],
        "mcp_enabled": mcp_enabled,
        "plugin_catalog": [
            p.model_dump() if hasattr(p, "model_dump") else p for p in plugin_catalog
        ],
    }
