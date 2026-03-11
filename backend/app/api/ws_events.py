"""WebSocket /ws/events - dashboard push events (GenUI, cross-client, status).

This is a **read-only** channel: the dashboard connects, authenticates,
and then receives a stream of JSON events published by the live audio
pipeline (``ws_live``) through an ``EventBus``.

Lifecycle
---------
1. Client opens ``ws://<host>/ws/events``
2. Client sends an ``AuthMessage`` JSON frame (Firebase JWT)
3. Server validates, replies with ``AuthResponse``
4. Server subscribes the socket to the user's event bus
5. Events pushed by ``ws_live`` are forwarded as JSON text frames
6. On disconnect - unsubscribe + cleanup
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.middleware.auth_middleware import AuthenticatedUser, _get_firebase_app
from app.models.ws_messages import AuthResponse
from app.services.event_bus import get_event_bus
from app.utils.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

router = APIRouter()


# ── Authentication (same pattern as ws_live) ──────────────────────────


async def _authenticate_ws(websocket: WebSocket) -> AuthenticatedUser | None:
    """Wait for the first JSON frame and validate as auth message."""
    from firebase_admin import auth as firebase_auth

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
    except (TimeoutError, WebSocketDisconnect):
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        await _send_auth_error(websocket, "Invalid JSON")
        return None

    if data.get("type") != "auth" or not data.get("token"):
        await _send_auth_error(websocket, "First message must be auth with token")
        return None

    _get_firebase_app()
    try:
        decoded = firebase_auth.verify_id_token(data["token"])
    except Exception:
        await _send_auth_error(websocket, "Invalid or expired token")
        return None

    return AuthenticatedUser(decoded)


async def _send_auth_error(websocket: WebSocket, error: str) -> None:
    msg = AuthResponse(status="error", error=error)
    await websocket.send_text(msg.model_dump_json())
    await websocket.close(code=4003, reason=error)


# ── Main WebSocket endpoint ──────────────────────────────────────────


@router.websocket("/events")
async def ws_events(websocket: WebSocket) -> None:
    """Read-only dashboard event stream."""
    await websocket.accept()

    # Phase 1 - Authenticate
    user = await _authenticate_ws(websocket)
    if user is None:
        return

    bus = get_event_bus()
    queue = bus.create_queue()

    # Phase 2 - Subscribe to user's event stream
    bus.subscribe(user.uid, queue)

    auth_ok = AuthResponse(status="ok", user_id=user.uid)
    await websocket.send_text(auth_ok.model_dump_json())

    # Phase 3 - Forward events until disconnect
    relay_task: asyncio.Task[None] | None = None
    try:
        relay_task = asyncio.create_task(_relay_events(websocket, queue))
        # Block until client disconnects
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws_events_error", user_id=user.uid)
    finally:
        if relay_task and not relay_task.done():
            relay_task.cancel()
        bus.unsubscribe(user.uid, queue)
        logger.info("ws_events_closed", user_id=user.uid)


async def _relay_events(websocket: WebSocket, queue: asyncio.Queue[str]) -> None:
    """Pull events from the queue and send to the WebSocket."""
    try:
        while True:
            event_json = await queue.get()
            await websocket.send_text(event_json)
    except asyncio.CancelledError:
        pass
