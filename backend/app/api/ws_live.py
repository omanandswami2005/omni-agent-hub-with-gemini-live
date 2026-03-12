"""WebSocket /ws/live — ADK bidi streaming (binary audio + JSON control).

Lifecycle
---------
1. Client opens ``ws://<host>/ws/live``
2. Client sends an ``AuthMessage`` JSON frame (Firebase JWT)
3. Server validates, replies with ``AuthResponse``
4. Two tasks run in parallel via ``asyncio.gather``:
   - **upstream** - receives binary PCM-16 audio + JSON control from client,
     pushes to ADK ``LiveRequestQueue``
   - **downstream** - receives ``Event`` objects from ADK ``runner.run_live()``,
     forwards binary audio + JSON text/transcription/status to client
5. On disconnect → cleanup queue, connection manager entry
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import warnings
from typing import TYPE_CHECKING

# Suppress Pydantic serialization warning for response_modalities.
# ADK's RunConfig stores modalities as list[str] but the downstream
# GenerationConfig expects Modality enums — this is an ADK-internal mismatch.
warnings.filterwarnings(
    "ignore",
    message="Pydantic serializer warnings",
    category=UserWarning,
    module=r"pydantic\.main",
)

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# ── Light imports only (no google.adk / google.genai at module level) ──
from app.config import settings
from app.middleware.auth_middleware import AuthenticatedUser, _get_firebase_app
from app.models.client import ClientType
from app.models.ws_messages import (
    AgentResponse,
    AgentState,
    AuthResponse,
    ConnectedMessage,
    ContentType,
    ImageResponseMessage,
    StatusMessage,
    ToolCallMessage,
    ToolResponseMessage,
    ToolStatus,
    TranscriptionDirection,
    TranscriptionMessage,
)
from app.services.connection_manager import get_connection_manager
from app.services.event_bus import EventBus, get_event_bus
from app.services.memory_service import get_memory_service
from app.services.mcp_manager import get_mcp_manager
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from google.adk.agents.live_request_queue import LiveRequestQueue
    from google.adk.agents.run_config import RunConfig
    from google.adk.events import Event
    from google.adk.runners import Runner
    from google.genai import types

logger = get_logger(__name__)

router = APIRouter()

# ── Module-level singletons (built lazily on first use) ───────────────

APP_NAME = "omni-hub"
AUDIO_INPUT_MIME = "audio/pcm;rate=16000"

_adk_session_service = None  # lazy — built on first call to _get_session_service()
_vertex_session_service = None  # lazy — for background persistence only


def _get_session_service():
    """Always returns InMemorySessionService for zero-latency run_live().

    VertexAiSessionService adds ~200-500ms per append_event() network call.
    During run_live(), ADK calls append_event for EVERY model event —
    this kills real-time audio latency.  We use InMemory for streaming
    and rely on:
      - Live API session resumption for cross-connection continuity
      - Memory bank sync for conversation persistence
      - Background Vertex AI persist for Agent Engine session history
    """
    global _adk_session_service
    if _adk_session_service is not None:
        return _adk_session_service

    from google.adk.sessions import InMemorySessionService
    _adk_session_service = InMemorySessionService()
    logger.info("session_service_init", backend="in_memory", reason="zero_latency_hot_path")
    return _adk_session_service


def _get_vertex_session_service():
    """Optional lazy singleton: VertexAiSessionService for background persistence.

    Only initialised when USE_AGENT_ENGINE_SESSIONS is True.  Never used
    in the hot path (run_live / run_async) — only for cold-path background
    persistence after the live session ends.
    """
    global _vertex_session_service
    if _vertex_session_service is not None:
        return _vertex_session_service
    if not settings.USE_AGENT_ENGINE_SESSIONS:
        return None

    try:
        from google.adk.sessions import VertexAiSessionService
        from app.services.agent_engine_service import get_agent_engine_service

        ae = get_agent_engine_service()
        agent_engine_id = ae.get_reasoning_engine_id()
        _vertex_session_service = VertexAiSessionService(
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
            agent_engine_id=agent_engine_id,
        )
        logger.info(
            "vertex_session_service_init",
            backend="vertex_ai",
            project=settings.GOOGLE_CLOUD_PROJECT,
            agent_engine_id=agent_engine_id,
        )
        return _vertex_session_service
    except Exception:
        logger.warning("vertex_session_service_init_failed", exc_info=True)
        return None


# ── Runner pool — cached per user_id ──────────────────────────────────

# Runner TTL: if a user hasn't reconnected within this window, the cached
# runner is discarded so that MCP tool changes are picked up.
_RUNNER_TTL = 10 * 60  # 10 minutes

# { user_id: (Runner, enabled_mcp_ids_frozenset, created_monotonic) }
_runner_cache: dict[str, tuple["Runner", frozenset[str], float]] = {}


async def _get_runner(user_id: str, session_service=None):
    """Return a Runner for *user_id*, reusing a cached one when possible.

    The cache is keyed by ``user_id``.  A cached runner is reused when:
    - It was created less than ``_RUNNER_TTL`` seconds ago, AND
    - The user's enabled MCP tool set hasn't changed since creation.

    Otherwise a fresh runner is built (and cached).
    """
    from google.adk.runners import Runner
    from app.agents.root_agent import build_root_agent

    ss = session_service or _get_session_service()

    mcp_mgr = get_mcp_manager()
    enabled_ids = frozenset(mcp_mgr.get_enabled_ids(user_id))

    cached = _runner_cache.get(user_id)
    if cached is not None:
        runner, cached_ids, ts = cached
        if time.monotonic() - ts < _RUNNER_TTL and cached_ids == enabled_ids:
            return runner
        # Stale or MCP set changed → discard
        _runner_cache.pop(user_id, None)

    # Evict expired entries from other users while we're here
    now = time.monotonic()
    expired = [uid for uid, (_, _, ts) in _runner_cache.items() if now - ts > _RUNNER_TTL]
    for uid in expired:
        _runner_cache.pop(uid, None)

    mcp_tools: list = []
    try:
        mcp_tools = await mcp_mgr.get_tools(user_id)
    except Exception:
        logger.warning("mcp_tools_load_failed", user_id=user_id, exc_info=True)

    root = build_root_agent(mcp_tools=mcp_tools)
    runner = Runner(
        app_name=APP_NAME,
        agent=root,
        session_service=ss,
    )
    _runner_cache[user_id] = (runner, enabled_ids, time.monotonic())
    logger.debug("runner_cached", user_id=user_id, mcp_count=len(mcp_tools))
    return runner


def invalidate_runner(user_id: str) -> None:
    """Remove a cached runner for *user_id* (e.g. after MCP toggle)."""
    _runner_cache.pop(user_id, None)
    _chat_runner_cache.pop(user_id, None)


# ── ADK session ID cache (Vertex assigns IDs; we cache per user) ──────

# { user_id: session_id }  — populated lazily on first connect
_adk_session_id_cache: dict[str, str] = {}


async def _get_or_create_adk_session(user_id: str, session_service=None) -> str:
    """Return the ADK session ID for *user_id*, creating one if needed.

    VertexAiSessionService does NOT accept user-provided session IDs —
    it assigns them on create.  We cache the assigned ID in memory so
    that reconnects reuse the same session (conversation continuity).

    On first call per user (or after a server restart):
      1. List existing sessions for the user — reuse the most-recent one.
      2. If none exist, create a fresh session and cache the new ID.
    """
    if user_id in _adk_session_id_cache:
        return _adk_session_id_cache[user_id]

    ss = session_service or _get_session_service()

    # Try to find an existing session first
    try:
        response = await ss.list_sessions(app_name=APP_NAME, user_id=user_id)
        sessions = getattr(response, "sessions", [])
        if sessions:
            # Pick the most recently updated session
            best = max(sessions, key=lambda s: getattr(s, "last_update_time", 0))
            _adk_session_id_cache[user_id] = best.id
            logger.info("adk_session_reused", user_id=user_id, session_id=best.id)
            return best.id
    except Exception:
        logger.warning("adk_session_list_failed", user_id=user_id, exc_info=True)

    # No existing session — create one (Vertex assigns the ID)
    session = await ss.create_session(app_name=APP_NAME, user_id=user_id)
    _adk_session_id_cache[user_id] = session.id
    logger.info("adk_session_created", user_id=user_id, session_id=session.id)
    return session.id


# ── Chat Runner pool — uses TEXT_MODEL for generateContent ────────────

_chat_runner_cache: dict[str, tuple["Runner", frozenset[str], float]] = {}


async def _get_chat_runner(user_id: str, session_service=None):
    """Return a Runner using TEXT_MODEL for the chat (non-live) endpoint."""
    from google.adk.runners import Runner
    from app.agents.root_agent import build_root_agent
    from app.agents.agent_factory import TEXT_MODEL

    ss = session_service or _get_session_service()

    mcp_mgr = get_mcp_manager()
    enabled_ids = frozenset(mcp_mgr.get_enabled_ids(user_id))

    cached = _chat_runner_cache.get(user_id)
    if cached is not None:
        runner, cached_ids, ts = cached
        if time.monotonic() - ts < _RUNNER_TTL and cached_ids == enabled_ids:
            return runner
        _chat_runner_cache.pop(user_id, None)

    mcp_tools: list = []
    try:
        mcp_tools = await mcp_mgr.get_tools(user_id)
    except Exception:
        logger.warning("mcp_tools_load_failed", user_id=user_id, exc_info=True)

    root = build_root_agent(mcp_tools=mcp_tools, model=TEXT_MODEL)
    runner = Runner(
        app_name=APP_NAME,
        agent=root,
        session_service=ss,
    )
    _chat_runner_cache[user_id] = (runner, enabled_ids, time.monotonic())
    logger.debug("chat_runner_cached", user_id=user_id, model=TEXT_MODEL, mcp_count=len(mcp_tools))
    return runner


def _build_run_config(voice: str = "Aoede"):
    """Build an ADK ``RunConfig`` for bidi live streaming."""
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.genai import types

    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice,
                ),
            ),
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(
            handle="",  # ADK fills this on first connect; empty string = new session
        ),
        context_window_compression=types.ContextWindowCompressionConfig(
            sliding_window=types.SlidingWindow(
                target_tokens=16_000,  # Must be ≤ trigger tokens (32k for native audio model)
            ),
        ),
        proactivity=types.ProactivityConfig(proactive_audio=True),
        enable_affective_dialog=True,
    )


# ── Authentication helper ─────────────────────────────────────────────


async def _authenticate_ws(websocket: WebSocket) -> tuple[AuthenticatedUser, ClientType, str, str] | None:
    """Wait for the first JSON frame and validate it as an auth message.

    Returns ``(AuthenticatedUser, client_type, os_name, requested_session_id)``
    on success, or ``None`` after sending an error and closing the socket.
    The ``requested_session_id`` is the **Firestore** session the client wants
    to resume (empty string if new).
    """
    from firebase_admin import auth as firebase_auth
    from app.models.client import ClientType

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
    except (TimeoutError, WebSocketDisconnect):
        logger.warning("ws_auth_timeout")
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
        decoded = firebase_auth.verify_id_token(data["token"], clock_skew_seconds=5)
    except Exception as exc:
        logger.warning("ws_auth_failed", client=websocket.client.host if websocket.client else "?", error=str(exc))
        await _send_auth_error(websocket, "Invalid or expired token")
        return None

    # Parse client_type from message, default to WEB
    client_type_str = data.get("client_type", "web").lower()
    try:
        client_type = ClientType(client_type_str)
    except ValueError:
        client_type = ClientType.WEB

    # Detect OS from user agent sent by the client
    from app.models.client import detect_os
    user_agent = data.get("user_agent", "")
    os_name = detect_os(user_agent)

    logger.info("ws_auth_ok", uid=decoded.get("uid"), client=client_type_str)

    # Optional: client can request to resume a specific Firestore session
    requested_session_id = data.get("session_id", "")

    return AuthenticatedUser(decoded), client_type, os_name, requested_session_id


async def _send_auth_error(websocket: WebSocket, error: str) -> None:
    msg = AuthResponse(status="error", error=error)
    with contextlib.suppress(Exception):
        await websocket.send_text(msg.model_dump_json())
    with contextlib.suppress(Exception):
        await websocket.close(code=4003, reason=error)


# ── Upstream (client → ADK) ──────────────────────────────────────────


async def _upstream(
    websocket: WebSocket,
    queue: LiveRequestQueue,
    user_id: str,
) -> None:
    """Receive frames from the client and push into the ADK queue.

    - **Binary frames** → PCM audio → ``send_realtime``
    - **JSON text frames** → control messages → ``send_content``
    """
    from google.genai import types

    try:
        while True:
            msg = await websocket.receive()
            if msg.get("bytes"):
                audio_blob = types.Blob(
                    mime_type=AUDIO_INPUT_MIME,
                    data=msg["bytes"],
                )
                queue.send_realtime(audio_blob)
            elif msg.get("text"):
                try:
                    data = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                msg_type = data.get("type", "")
                if msg_type == "text":
                    content = types.Content(
                        parts=[types.Part(text=data.get("content", ""))],
                        role="user",
                    )
                    queue.send_content(content)
                elif msg_type == "image":
                    import base64

                    image_bytes = base64.b64decode(data.get("data_base64", ""))
                    blob = types.Blob(
                        mime_type=data.get("mime_type", "image/jpeg"),
                        data=image_bytes,
                    )
                    queue.send_realtime(blob)
                elif msg_type == "mcp_toggle":
                    # Handle MCP toggle during live session
                    mcp_id = data.get("mcp_id")
                    enabled = data.get("enabled", False)
                    if mcp_id:
                        mcp_mgr = get_mcp_manager()
                        from app.models.mcp import MCPToggle
                        toggle = MCPToggle(mcp_id=mcp_id, enabled=enabled)
                        try:
                            await mcp_mgr.toggle_mcp(user_id, toggle)
                            invalidate_runner(user_id)
                            logger.info("mcp_toggle_during_session", user_id=user_id, mcp_id=mcp_id, enabled=enabled)
                        except Exception:
                            logger.warning("mcp_toggle_failed", user_id=user_id, mcp_id=mcp_id, exc_info=True)
                # Other control messages (persona_switch)
                # are handled at the API layer, not pushed to ADK
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError fires when the WS is replaced by a new connection
        logger.info("ws_upstream_disconnected", user_id=user_id)
    except Exception:
        logger.exception("ws_upstream_error", user_id=user_id)
    finally:
        queue.close()  # Signal run_live() to stop gracefully


# ── Downstream (ADK → client) ────────────────────────────────────────


async def _downstream(
    websocket: WebSocket,
    runner: Runner,
    user_id: str,
    session_id: str,
    queue: LiveRequestQueue,
    run_config: RunConfig,
) -> None:
    """Stream events from ``run_live()`` back to the client.

    - Audio parts → binary frames (raw PCM 24kHz)
    - Text parts → ``AgentResponse`` JSON
    - Transcriptions → ``TranscriptionMessage`` JSON
    - Tool calls → ``ToolCallMessage`` / ``ToolResponseMessage`` JSON
    - Status changes → ``StatusMessage`` JSON

    Non-audio events are also published to the ``EventBus`` for
    connected dashboard clients.
    """
    bus = get_event_bus()
    first_event = True
    try:
        async for event in runner.run_live(
            user_id=user_id,
            session_id=session_id,
            live_request_queue=queue,
            run_config=run_config,
        ):
            if first_event:
                logger.info("live_connection_established", user_id=user_id, session_id=session_id)
                first_event = False
            await _process_event(websocket, event, bus, user_id)
    except (WebSocketDisconnect, RuntimeError):
        logger.info("ws_downstream_disconnected", user_id=user_id)
    except Exception as exc:
        # Classify expected WebSocket closure conditions as info, not errors.
        exc_str = str(exc)
        normal_closure = (
            # Graceful cancel from Gemini side
            ("1000" in exc_str and "cancelled" in exc_str.lower())
            # Keepalive ping timeout — network drop between backend and Gemini
            or "keepalive ping timeout" in exc_str.lower()
            # Any other normal close (1001 going away, 1006 abnormal)
            or "connection closed" in exc_str.lower()
        )
        if normal_closure:
            logger.info("ws_downstream_session_ended", user_id=user_id, reason=exc_str)
        else:
            logger.exception("ws_downstream_error", user_id=user_id)


async def _process_event(
    websocket: WebSocket,
    event: Event,
    bus: EventBus | None = None,
    user_id: str = "",
) -> None:
    """Translate a single ADK Event into WebSocket frames.

    Non-audio JSON messages are also published to *bus* so that
    connected dashboard clients receive real-time updates.
    """
    # ── Audio output ──────────────────────────────────────────────
    if event.content and event.content.parts:
        for part in event.content.parts:
            if part.inline_data and part.inline_data.data:
                # Raw PCM audio → binary frame (NOT forwarded to dashboard)
                await websocket.send_bytes(part.inline_data.data)
            elif part.text:
                msg = AgentResponse(
                    content_type=ContentType.TEXT,
                    data=part.text,
                )
                json_str = msg.model_dump_json()
                await websocket.send_text(json_str)
                await _publish(bus, user_id, json_str)

    # ── Transcription ─────────────────────────────────────────────
    if event.input_transcription and event.input_transcription.text:
        msg = TranscriptionMessage(
            direction=TranscriptionDirection.INPUT,
            text=event.input_transcription.text,
            finished=event.input_transcription.finished or False,
        )
        json_str = msg.model_dump_json()
        await websocket.send_text(json_str)
        await _publish(bus, user_id, json_str)

    if event.output_transcription and event.output_transcription.text:
        msg = TranscriptionMessage(
            direction=TranscriptionDirection.OUTPUT,
            text=event.output_transcription.text,
            finished=event.output_transcription.finished or False,
        )
        json_str = msg.model_dump_json()
        await websocket.send_text(json_str)
        await _publish(bus, user_id, json_str)

    # ── Tool calls ────────────────────────────────────────────────
    for fc in event.get_function_calls():
        msg = ToolCallMessage(
            tool_name=fc.name,
            arguments=dict(fc.args) if fc.args else {},
            status=ToolStatus.STARTED,
        )
        json_str = msg.model_dump_json()
        await websocket.send_text(json_str)
        await _publish(bus, user_id, json_str)

    # ── Tool responses + image delivery ─────────────────────────────
    #
    # Image tools (generate_image / generate_rich_image) return TEXT ONLY
    # to Gemini (saves context tokens).  Actual image data is queued in
    # ``image_gen._pending_images`` during tool execution and drained here
    # when we see the corresponding function_response event.
    #
    from app.tools.image_gen import IMAGE_TOOL_NAMES, drain_pending_images

    for fr in event.get_function_responses():
        # Drain pending images queued by the tool for this user
        if fr.name in IMAGE_TOOL_NAMES and user_id:
            for img_data in drain_pending_images(user_id):
                img_msg = ImageResponseMessage(**img_data)
                json_str = img_msg.model_dump_json()
                await websocket.send_text(json_str)
                await _publish(bus, user_id, json_str)

        # Always send the tool response (text summary for image tools)
        msg = ToolResponseMessage(
            tool_name=fr.name,
            result=str(fr.response) if fr.response else "",
            success=True,
        )
        json_str = msg.model_dump_json()
        await websocket.send_text(json_str)
        await _publish(bus, user_id, json_str)

    # ── Turn complete / interrupted ───────────────────────────────
    if event.turn_complete:
        msg = StatusMessage(state=AgentState.IDLE)
        json_str = msg.model_dump_json()
        await websocket.send_text(json_str)
        await _publish(bus, user_id, json_str)
    elif event.interrupted:
        msg = StatusMessage(state=AgentState.LISTENING, detail="Interrupted by user")
        json_str = msg.model_dump_json()
        await websocket.send_text(json_str)
        await _publish(bus, user_id, json_str)


async def _publish(bus: EventBus | None, user_id: str, json_str: str) -> None:
    """Publish to the event bus if available."""
    if bus and user_id:
        await bus.publish(user_id, json_str)


# ── Background Vertex AI session persistence ─────────────────────────


async def _background_persist_to_vertex(
    user_id: str,
    session_id: str,
    in_memory_service,
) -> str | None:
    """Copy session events from InMemory → Vertex AI.

    Called after a live session ends.  Returns the Vertex session resource
    name on success (used for memory generation), or *None* on failure.
    """
    try:
        vertex_ss = _get_vertex_session_service()
        if vertex_ss is None:
            return None

        # Retrieve the in-memory session (still alive in the singleton dict)
        session = await in_memory_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id,
        )
        if session is None or not session.events:
            logger.debug("vertex_persist_skip_no_events", user_id=user_id)
            return None

        # Create a new Vertex session to hold the persisted events
        vertex_session = await vertex_ss.create_session(
            app_name=APP_NAME, user_id=user_id,
        )

        persisted = 0
        for event in session.events:
            try:
                await vertex_ss.append_event(session=vertex_session, event=event)
                persisted += 1
            except Exception:
                # Skip individual events that fail (e.g. unsupported blob types)
                continue

        logger.info(
            "vertex_session_persisted",
            user_id=user_id,
            vertex_session_id=vertex_session.id,
            events_total=len(session.events),
            events_persisted=persisted,
        )
        return vertex_session.id
    except Exception:
        logger.warning(
            "vertex_session_persist_failed",
            user_id=user_id,
            session_id=session_id,
            exc_info=True,
        )
        return None


# ── Main WebSocket endpoint ──────────────────────────────────────────


@router.websocket("/live")
async def ws_live(websocket: WebSocket) -> None:
    """Bidirectional audio streaming with Gemini via ADK."""
    await websocket.accept()

    # Phase 1 — Authenticate (includes client_type detection)
    auth_result = await _authenticate_ws(websocket)
    if auth_result is None:
        return
    user, client_type, os_name, requested_session_id = auth_result

    mgr = get_connection_manager()
    
    # Check if OTHER client types are already online (for session continuity)
    other_clients = mgr.get_other_clients_online(user.uid, client_type)
    
    # Phase 2 — Register connection + prepare ADK session
    await mgr.connect(websocket, user.uid, client_type, os_name=os_name)
    
    # Get or create the ADK session (InMemory; we cache the ID)
    active_session_service = _get_session_service()
    session_id = await _get_or_create_adk_session(user.uid, active_session_service)

    # Create/link Firestore session to ADK session (non-blocking best-effort)
    from app.services.session_service import get_session_service as _get_fs_svc
    from app.models.session import SessionCreate
    _fs_svc = _get_fs_svc()
    firestore_session_id = None
    try:
        if requested_session_id:
            # Client wants to resume a specific Firestore session
            fs_session = await _fs_svc.get_session(user.uid, requested_session_id)
            firestore_session_id = fs_session.id
            if not fs_session.adk_session_id:
                await _fs_svc.link_adk_session(firestore_session_id, session_id)
        else:
            fs_session = await _fs_svc.create_session(user.uid, SessionCreate())
            firestore_session_id = fs_session.id
            await _fs_svc.link_adk_session(firestore_session_id, session_id)
    except Exception:
        # Requested session not found or creation failed — create a new one
        try:
            fs_session = await _fs_svc.create_session(user.uid, SessionCreate())
            firestore_session_id = fs_session.id
            await _fs_svc.link_adk_session(firestore_session_id, session_id)
        except Exception:
            logger.debug("firestore_session_link_failed", user_id=user.uid)

    # Determine voice from active persona (default: first default persona)
    from app.agents.personas import get_default_personas
    default_persona = get_default_personas()[0]
    run_config = _build_run_config(voice=default_persona.voice)

    # Send auth success + connected message
    auth_ok = AuthResponse(
        status="ok", user_id=user.uid, session_id=session_id,
        firestore_session_id=firestore_session_id or "",
    )
    connected = ConnectedMessage(session_id=session_id)
    await websocket.send_text(auth_ok.model_dump_json())
    await websocket.send_text(connected.model_dump_json())

    # If other clients are online, suggest session continuation
    if other_clients:
        from app.models.ws_messages import SessionSuggestionMessage
        suggestion = SessionSuggestionMessage(
            available_clients=[str(ct) for ct in other_clients],
            message=f"You're already active on {', '.join(str(ct) for ct in other_clients)}. Join that session for uninterrupted context?"
        )
        await websocket.send_text(suggestion.model_dump_json())

    # Phase 3 — Bidi streaming
    from google.adk.agents.live_request_queue import LiveRequestQueue
    queue = LiveRequestQueue()
    runner = await _get_runner(user.uid, session_service=active_session_service)

    logger.info(
        "live_session_ready",
        user_id=user.uid,
        session_id=session_id,
        client_type=str(client_type),
    )

    up_task: asyncio.Task | None = None
    down_task: asyncio.Task | None = None
    try:
        up_task = asyncio.create_task(
            _upstream(websocket, queue, user.uid), name="upstream",
        )
        down_task = asyncio.create_task(
            _downstream(websocket, runner, user.uid, session_id, queue, run_config),
            name="downstream",
        )
        # When either task finishes (disconnect or error), cancel the other
        done, pending = await asyncio.wait(
            {up_task, down_task}, return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        # Await pending tasks to let them clean up
        await asyncio.gather(*pending, return_exceptions=True)
        # Re-raise if the completed task had an unexpected exception
        for task in done:
            if task.exception() and not isinstance(task.exception(), asyncio.CancelledError):
                logger.warning("ws_task_error", user_id=user.uid, task=task.get_name(), exc_info=task.exception())
    except asyncio.CancelledError:
        logger.info("ws_live_cancelled", user_id=user.uid)
    except Exception:
        logger.exception("ws_live_error", user_id=user.uid)
    finally:
        # Phase 4 — Cleanup
        queue.close()  # Ensure queue is closed (upstream also closes, but be safe)

        # Persist session to Vertex AI first so memory sync can reference it.
        # Memory generation requires a valid Vertex AI session resource name.
        vertex_session_id: str | None = None
        if settings.USE_AGENT_ENGINE_SESSIONS:
            vertex_session_id = await _background_persist_to_vertex(
                user.uid, session_id, active_session_service,
            )

        # Generate memories from the Vertex session (not the InMemory one)
        if vertex_session_id:
            try:
                await get_memory_service().sync_from_session(user.uid, vertex_session_id)
            except Exception as exc:
                exc_str = str(exc).lower()
                if "throttled" in exc_str or "quota" in exc_str or "resource_exhausted" in exc_str:
                    logger.debug("memory_bank_sync_throttled", user_id=user.uid, session_id=session_id)
                else:
                    logger.warning("memory_bank_sync_failed", user_id=user.uid, session_id=session_id, exc_info=True)

        await mgr.disconnect(user.uid, client_type)
        logger.info("ws_live_closed", user_id=user.uid, session_id=session_id)


# ── Text-only chat WebSocket (/ws/chat) ───────────────────────────────────
#
# Provides a reliable ADK-powered text chat channel that works even when the
# Gemini Live audio connection is unavailable or disconnected.
#
# Protocol:
#   1. Client connects and sends Auth frame (same as /ws/live)
#   2. Client sends: {"type":"text","content":"Hello"}
#   3. Server responds with AgentResponse JSON frames + tool events
#   4. Server signals completion with StatusMessage(state=idle)
#

@router.websocket("/chat")
async def ws_chat(websocket: WebSocket) -> None:
    """ADK text-only chat over WebSocket — no audio, no live session required."""
    from google.adk.runners import Runner
    from google.genai import types

    await websocket.accept()

    auth_result = await _authenticate_ws(websocket)
    if auth_result is None:
        return
    user, client_type, os_name, requested_session_id = auth_result

    active_session_service = _get_session_service()
    session_id = await _get_or_create_adk_session(user.uid, active_session_service)

    # Link Firestore session to ADK session
    from app.services.session_service import get_session_service as _get_fs_svc
    from app.models.session import SessionCreate
    _fs_svc = _get_fs_svc()
    firestore_session_id = None
    try:
        if requested_session_id:
            # Client wants to resume a specific Firestore session
            fs_session = await _fs_svc.get_session(user.uid, requested_session_id)
            firestore_session_id = fs_session.id
            if not fs_session.adk_session_id:
                await _fs_svc.link_adk_session(firestore_session_id, session_id)
        else:
            latest = await _fs_svc.get_latest_session_for_user(user.uid)
            if latest and latest.adk_session_id == session_id:
                firestore_session_id = latest.id
            else:
                fs_session = await _fs_svc.create_session(user.uid, SessionCreate())
                firestore_session_id = fs_session.id
                await _fs_svc.link_adk_session(fs_session.id, session_id)
    except Exception:
        try:
            fs_session = await _fs_svc.create_session(user.uid, SessionCreate())
            firestore_session_id = fs_session.id
            await _fs_svc.link_adk_session(fs_session.id, session_id)
        except Exception:
            logger.debug("firestore_session_link_failed_chat", user_id=user.uid)

    auth_ok = AuthResponse(
        status="ok", user_id=user.uid, session_id=session_id,
        firestore_session_id=firestore_session_id or "",
    )
    await websocket.send_text(auth_ok.model_dump_json())

    bus = get_event_bus()
    runner = await _get_chat_runner(user.uid, session_service=active_session_service)

    logger.info("ws_chat_connected", user_id=user.uid, session_id=session_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("type") != "text" or not data.get("content", "").strip():
                continue

            content = types.Content(
                parts=[types.Part(text=data["content"])],
                role="user",
            )

            # Status: thinking
            thinking_msg = StatusMessage(state=AgentState.PROCESSING)
            await websocket.send_text(thinking_msg.model_dump_json())

            try:
                async for event in runner.run_async(
                    user_id=user.uid,
                    session_id=session_id,
                    new_message=content,
                ):
                    await _process_event(websocket, event, bus, user.uid)
                # run_async events don't carry turn_complete, so send IDLE explicitly
                idle_msg = StatusMessage(state=AgentState.IDLE)
                await websocket.send_text(idle_msg.model_dump_json())
            except Exception:
                logger.exception("ws_chat_turn_error", user_id=user.uid)
                err_msg = StatusMessage(state=AgentState.IDLE)
                await websocket.send_text(err_msg.model_dump_json())

    except (WebSocketDisconnect, RuntimeError):
        logger.info("ws_chat_disconnected", user_id=user.uid)
    except Exception:
        logger.exception("ws_chat_error", user_id=user.uid)
    finally:
        # Persist chat session to Vertex + generate memories (same as ws_live)
        vertex_session_id: str | None = None
        if settings.USE_AGENT_ENGINE_SESSIONS:
            vertex_session_id = await _background_persist_to_vertex(
                user.uid, session_id, active_session_service,
            )
        if vertex_session_id:
            try:
                await get_memory_service().sync_from_session(user.uid, vertex_session_id)
            except Exception:
                logger.warning("memory_bank_sync_failed_chat", user_id=user.uid, exc_info=True)

        logger.info("ws_chat_closed", user_id=user.uid, session_id=session_id)
