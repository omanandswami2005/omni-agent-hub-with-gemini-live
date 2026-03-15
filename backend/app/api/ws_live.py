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
import contextvars
import json
import re
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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect  # noqa: E402

from app.config import settings  # noqa: E402
from app.middleware.auth_middleware import AuthenticatedUser, _get_firebase_app  # noqa: E402
from app.models.client import ClientType  # noqa: E402
from app.models.ws_messages import (  # noqa: E402
    ActionKind,
    AgentResponse,
    AgentState,
    AgentTransferMessage,
    AuthResponse,
    ConnectedMessage,
    ContentType,
    ErrorMessage,
    ImageResponseMessage,
    StatusMessage,
    ToolCallMessage,
    ToolResponseMessage,
    ToolStatus,
    TranscriptionDirection,
    TranscriptionMessage,
)
from app.services.connection_manager import get_connection_manager  # noqa: E402
from app.services.event_bus import EventBus, get_event_bus  # noqa: E402
from app.services.mcp_manager import get_mcp_manager  # noqa: E402
from app.services.memory_service import get_memory_service  # noqa: E402
from app.utils.logging import get_logger  # noqa: E402

# Per-task context variable: set to `str(id(websocket))` inside every
# _process_event() call so _publish() can stamp the origin connection.
# Subscribers (e.g. the ws_chat relay task) use this to drop their own echoes.
_conn_tag_var: contextvars.ContextVar[str] = contextvars.ContextVar("conn_tag", default="")
# Per-task context variable: set to the client_type string in _process_event()
# so _publish() can embed _origin_client_type in every EventBus event.
_client_type_var: contextvars.ContextVar[str] = contextvars.ContextVar("client_type", default="")

if TYPE_CHECKING:
    from google.adk.agents.live_request_queue import LiveRequestQueue
    from google.adk.agents.run_config import RunConfig
    from google.adk.events import Event
    from google.adk.runners import Runner

logger = get_logger(__name__)

router = APIRouter()

# ── Background task tracking (prevents RUF006 / GC of fire-and-forget tasks) ──
_background_tasks: set[asyncio.Task] = set()


def _fire_and_forget(coro) -> asyncio.Task:
    """Schedule *coro* as a background task and prevent GC until done."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


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

# { user_id: (Runner, cache_key_tuple, created_monotonic) }
_runner_cache: dict[str, tuple[Runner, tuple, float]] = {}
_runner_lock = asyncio.Lock()


async def _get_runner(user_id: str, session_service=None):
    """Return a Runner for *user_id*, reusing a cached one when possible.

    The cache is keyed by ``user_id``.  A cached runner is reused when:
    - It was created less than ``_RUNNER_TTL`` seconds ago, AND
    - The user's enabled MCP tool set hasn't changed since creation.

    Otherwise a fresh runner is built (and cached).
    """
    from google.adk.runners import Runner

    from app.agents.personas import get_default_personas
    from app.agents.root_agent import build_root_agent

    ss = session_service or _get_session_service()

    from app.services.plugin_registry import get_plugin_registry

    enabled_ids = frozenset(get_plugin_registry().get_enabled_ids(user_id))

    # Include T3 tool names in cache key so runner rebuilds when clients connect/disconnect
    from app.services.tool_registry import get_tool_registry

    t3_names = frozenset(get_tool_registry().get_t3_tool_names(user_id))
    cache_key = (enabled_ids, t3_names)

    async with _runner_lock:
        cached = _runner_cache.get(user_id)
        if cached is not None:
            runner, cached_key, ts = cached
            if time.monotonic() - ts < _RUNNER_TTL and cached_key == cache_key:
                return runner
            # Stale or tool set changed → discard
            _runner_cache.pop(user_id, None)

        # Evict expired entries from other users while we're here
        now = time.monotonic()
        expired = [uid for uid, (_, _, ts) in _runner_cache.items() if now - ts > _RUNNER_TTL]
        for uid in expired:
            _runner_cache.pop(uid, None)

        # Build per-persona T2+T3 tool map
        personas = get_default_personas()
        tools_by_persona: dict[str, list] = {}
        try:
            tools_by_persona = await get_tool_registry().build_for_session(user_id, personas)
        except Exception:
            logger.warning("tool_registry_build_failed", user_id=user_id, exc_info=True)

        root = build_root_agent(
            personas=personas,
            tools_by_persona=tools_by_persona,
            plugin_summaries=get_plugin_registry().get_tool_summaries(user_id),
        )
        runner = Runner(
            app_name=APP_NAME,
            agent=root,
            session_service=ss,
        )
        t2_total = sum(len(v) for k, v in tools_by_persona.items() if k != "__device__")
        _runner_cache[user_id] = (runner, cache_key, time.monotonic())
        logger.debug("runner_cached", user_id=user_id, t2_tool_count=t2_total)
        return runner


def invalidate_runner(user_id: str) -> None:
    """Remove a cached runner for *user_id* (e.g. after MCP toggle)."""
    had_live = _runner_cache.pop(user_id, None) is not None
    had_chat = _chat_runner_cache.pop(user_id, None) is not None
    if had_live or had_chat:
        logger.info(
            "runner_invalidated",
            user_id=user_id,
            live=had_live,
            chat=had_chat,
        )


# ── ADK session ID cache (Vertex assigns IDs; we cache per user) ──────

# { user_id: session_id }  — populated lazily on first connect
_adk_session_id_cache: dict[str, str] = {}
_adk_session_lock = asyncio.Lock()


async def _adk_session_exists(session_id: str, user_id: str, session_service=None) -> bool:
    """Check whether *session_id* exists in the ADK session store."""
    ss = session_service or _get_session_service()
    try:
        s = await ss.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        return s is not None
    except Exception:
        return False


async def _get_or_create_adk_session(
    user_id: str, session_service=None, *, force_new: bool = False
) -> str:
    """Return the ADK session ID for *user_id*, creating one if needed.

    VertexAiSessionService does NOT accept user-provided session IDs —
    it assigns them on create.  We cache the assigned ID in memory so
    that reconnects reuse the same session (conversation continuity).

    When *force_new* is True, always create a fresh session (used when the
    user explicitly starts a new conversation).

    On first call per user (or after a server restart):
      1. List existing sessions for the user — reuse the most-recent one.
      2. If none exist, create a fresh session and cache the new ID.
    """
    async with _adk_session_lock:
        if not force_new and user_id in _adk_session_id_cache:
            sid = _adk_session_id_cache[user_id]
            # Verify the session actually exists in the service (it may
            # have been lost if Cloud Run cold-started a new instance).
            if await _adk_session_exists(sid, user_id, session_service):
                return sid
            # Stale — drop and fall through to create a new one
            _adk_session_id_cache.pop(user_id, None)

        ss = session_service or _get_session_service()

        if not force_new:
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

        # No existing session or force_new — create one
        session = await ss.create_session(app_name=APP_NAME, user_id=user_id)
        _adk_session_id_cache[user_id] = session.id
        logger.info("adk_session_created", user_id=user_id, session_id=session.id)
        return session.id


# ── Chat Runner pool — uses TEXT_MODEL for generateContent ────────────

_chat_runner_cache: dict[str, tuple[Runner, tuple, float]] = {}
_chat_runner_lock = asyncio.Lock()


async def _get_chat_runner(user_id: str, session_service=None):
    """Return a Runner using TEXT_MODEL for the chat (non-live) endpoint."""
    from google.adk.runners import Runner

    from app.agents.agent_factory import TEXT_MODEL
    from app.agents.personas import get_default_personas
    from app.agents.root_agent import build_root_agent

    ss = session_service or _get_session_service()

    from app.services.plugin_registry import get_plugin_registry

    enabled_ids = frozenset(get_plugin_registry().get_enabled_ids(user_id))

    from app.services.tool_registry import get_tool_registry

    t3_names = frozenset(get_tool_registry().get_t3_tool_names(user_id))
    cache_key = (enabled_ids, t3_names)

    async with _chat_runner_lock:
        cached = _chat_runner_cache.get(user_id)
        if cached is not None:
            runner, cached_key, ts = cached
            if time.monotonic() - ts < _RUNNER_TTL and cached_key == cache_key:
                return runner
            _chat_runner_cache.pop(user_id, None)

        personas = get_default_personas()
        tools_by_persona: dict[str, list] = {}
        try:
            tools_by_persona = await get_tool_registry().build_for_session(user_id, personas)
        except Exception:
            logger.warning("tool_registry_build_failed_chat", user_id=user_id, exc_info=True)

        root = build_root_agent(
            personas=personas,
            tools_by_persona=tools_by_persona,
            model=TEXT_MODEL,
            plugin_summaries=get_plugin_registry().get_tool_summaries(user_id),
        )
        runner = Runner(
            app_name=APP_NAME,
            agent=root,
            session_service=ss,
        )
        t2_total = sum(len(v) for k, v in tools_by_persona.items() if k != "__device__")
        _chat_runner_cache[user_id] = (runner, cache_key, time.monotonic())
        logger.debug(
            "chat_runner_cached", user_id=user_id, model=TEXT_MODEL, t2_tool_count=t2_total
        )
        return runner


def _build_run_config(voice: str = "Aoede", voice_enabled: bool = True):
    """Build an ADK ``RunConfig`` for bidi live streaming."""
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.genai import types

    modalities = ["AUDIO"] if voice_enabled else ["TEXT"]

    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=modalities,
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice,
                ),
            ),
        )
        if voice_enabled
        else None,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(
            handle="",  # ADK fills this on first connect; empty string = new session
        ),
        context_window_compression=types.ContextWindowCompressionConfig(
            trigger_tokens=100_000,
            sliding_window=types.SlidingWindow(
                target_tokens=80_000,
            ),
        ),
        proactivity=types.ProactivityConfig(proactive_audio=True),
        enable_affective_dialog=True,
    )


# ── Authentication helper ─────────────────────────────────────────────


async def _authenticate_ws(
    websocket: WebSocket,
) -> tuple[AuthenticatedUser, ClientType, str, str, list[str], list[dict], str, str] | None:
    """Wait for the first JSON frame and validate it as an auth message.

    Returns ``(AuthenticatedUser, client_type, os_name, requested_session_id, capabilities, local_tools, persona_id, voice_name)``
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
        logger.warning(
            "ws_auth_failed",
            client=websocket.client.host if websocket.client else "?",
            error=str(exc),
        )
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

    # Parse capabilities + local_tools from auth message
    capabilities = data.get("capabilities", [])
    local_tools = data.get("local_tools", [])

    logger.info(
        "ws_auth_ok",
        uid=decoded.get("uid"),
        client=client_type_str,
        capabilities=len(capabilities),
        local_tools=len(local_tools),
    )

    # Optional: client can request to resume a specific Firestore session
    requested_session_id = data.get("session_id", "")

    # Optional: client can request a specific persona (for voice selection)
    persona_id = data.get("persona_id", "")

    # Optional: client can override the voice directly
    voice_name = data.get("voice", "")

    return (
        AuthenticatedUser(decoded),
        client_type,
        os_name,
        requested_session_id,
        capabilities,
        local_tools,
        persona_id,
        voice_name,
    )


async def _send_auth_error(websocket: WebSocket, error: str) -> None:
    msg = AuthResponse(status="error", error=error)
    with contextlib.suppress(Exception):
        await websocket.send_text(msg.model_dump_json())
    with contextlib.suppress(Exception):
        await websocket.close(code=4003, reason=error)


# ── Upstream (client → ADK) ──────────────────────────────────────────


async def _increment_msg_count(firestore_session_id: str) -> None:
    """Best-effort increment of message_count on a Firestore session."""
    try:
        from app.services.session_service import get_session_service as _get_fs_svc

        await _get_fs_svc().increment_message_count(firestore_session_id)
    except Exception:
        pass  # Non-critical — silently ignore


async def _lazy_create_firestore_session(
    fs_id_ref: list[str | None],
    user_id: str,
    adk_session_id: str | None,
    websocket: WebSocket,
    first_content: str = "",
) -> str | None:
    """Create a Firestore session on first user activity (lazy).

    *fs_id_ref* is a single-element list used as a mutable reference so the
    caller's variable is updated in place.  If a session already exists,
    returns immediately.  Otherwise creates one, links ADK, and notifies
    the client with a ``session_created`` message.
    """
    if fs_id_ref[0]:
        return fs_id_ref[0]
    try:
        from app.models.session import SessionCreate
        from app.services.session_service import get_session_service as _get_fs_svc

        svc = _get_fs_svc()
        fs = await svc.create_session(user_id, SessionCreate())
        fs_id_ref[0] = fs.id
        if adk_session_id:
            await svc.link_adk_session(fs.id, adk_session_id)
        # Notify client of the new session ID
        with contextlib.suppress(Exception):
            await websocket.send_text(json.dumps({
                "type": "session_created",
                "firestore_session_id": fs.id,
            }))
        logger.info("lazy_session_created", user_id=user_id, session_id=fs.id)
        # Auto-generate title from first content (non-blocking)
        if first_content.strip():
            _fire_and_forget(svc.generate_title_from_message(fs.id, first_content))
        return fs.id
    except Exception:
        logger.warning("lazy_session_create_failed", user_id=user_id, exc_info=True)
        return None


async def _upstream(
    websocket: WebSocket,
    queue: LiveRequestQueue,
    user_id: str,
    client_type: ClientType | None = None,
    firestore_session_id_ref: list[str | None] | None = None,
    conn_tag: str = "",
    adk_session_id: str | None = None,
) -> None:
    """Receive frames from the client and push into the ADK queue.

    - **Binary frames** → PCM audio → ``send_realtime``
    - **JSON text frames** → control messages → ``send_content``
    """
    _upstream_client_type = client_type or ClientType.WEB
    _title_generated = False
    _holds_mic_floor = False  # True once this connection has acquired the floor
    _busy_notified = False    # Limit busy notifications to once per "episode"
    # Mutable ref so lazy session creation can update the ID
    _fs_ref = firestore_session_id_ref if firestore_session_id_ref is not None else [None]
    from google.genai import types

    try:
        while True:
            msg = await websocket.receive()
            if msg.get("bytes"):
                mgr = get_connection_manager()
                if not _holds_mic_floor:
                    # Fallback auto-acquire: for clients that don't send mic_acquire first.
                    if mgr.try_acquire_mic_floor(user_id, _upstream_client_type):
                        _holds_mic_floor = True
                        _busy_notified = False
                        floor_msg = json.dumps({
                            "type": "mic_floor",
                            "event": "acquired",
                            "holder": str(_upstream_client_type),
                        })
                        _fire_and_forget(mgr.send_to_user(user_id, floor_msg))
                    else:
                        # Another device holds the floor — notify once then drop silently
                        if not _busy_notified:
                            _busy_notified = True
                            holder = mgr.get_mic_floor_holder(user_id)
                            busy_msg = json.dumps({
                                "type": "mic_floor",
                                "event": "busy",
                                "holder": str(holder) if holder else "unknown",
                            })
                            with contextlib.suppress(Exception):
                                await websocket.send_text(busy_msg)
                        continue  # drop this audio frame
                else:
                    # Keep the stale-lock watchdog alive on every frame
                    mgr.touch_mic_floor(user_id, _upstream_client_type)
                audio_blob = types.Blob(
                    mime_type=AUDIO_INPUT_MIME,
                    data=msg["bytes"],
                )
                queue.send_realtime(audio_blob)
                # Lazy Firestore session creation on first audio frame
                if not _fs_ref[0]:
                    await _lazy_create_firestore_session(
                        _fs_ref, user_id, adk_session_id, websocket, "[voice]"
                    )
            elif msg.get("text"):
                try:
                    data = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                msg_type = data.get("type", "")
                if msg_type == "text":
                    content_str = data.get("content", "")
                    content = types.Content(
                        parts=[types.Part(text=content_str)],
                        role="user",
                    )
                    queue.send_content(content)
                    # Lazy Firestore session creation on first user message
                    if not _fs_ref[0] and content_str.strip():
                        await _lazy_create_firestore_session(
                            _fs_ref, user_id, adk_session_id, websocket, content_str
                        )
                        _title_generated = True  # title generated inside lazy create
                    # Publish text to EventBus for cross-client sync
                    bus = get_event_bus()
                    if bus and user_id:
                        user_msg = {
                            "type": "user_message",
                            "content": content_str,
                            "_origin_conn": conn_tag,
                            "_origin_client_type": str(_upstream_client_type) if _upstream_client_type else "",
                        }
                        _fire_and_forget(bus.publish(user_id, json.dumps(user_msg)))
                    # Increment message count (best-effort, non-blocking)
                    if _fs_ref[0]:
                        _fire_and_forget(_increment_msg_count(_fs_ref[0]))
                    # Auto-generate session title from first text message
                    if not _title_generated and _fs_ref[0] and content_str.strip():
                        _title_generated = True
                        from app.services.session_service import get_session_service as _get_fs_svc
                        _fire_and_forget(
                            _get_fs_svc().generate_title_from_message(_fs_ref[0], content_str)
                        )
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
                            logger.info(
                                "mcp_toggle_during_session",
                                user_id=user_id,
                                mcp_id=mcp_id,
                                enabled=enabled,
                            )
                        except Exception:
                            logger.warning(
                                "mcp_toggle_failed", user_id=user_id, mcp_id=mcp_id, exc_info=True
                            )
                elif msg_type == "tool_result":
                    # T3 reverse-RPC: client returning a tool result
                    from app.services.tool_registry import resolve_tool_result

                    call_id = data.get("call_id", "")
                    result = data.get("result", {})
                    error = data.get("error", "")
                    if call_id:
                        resolved = resolve_tool_result(call_id, result, error)
                        if not resolved:
                            logger.warning("t3_result_orphaned", user_id=user_id, call_id=call_id)
                elif msg_type == "capability_update":
                    # Client updating capabilities mid-session
                    mgr = get_connection_manager()
                    # We need client_type — stored in closure by the caller
                    mgr.update_capabilities(
                        user_id,
                        _upstream_client_type,
                        added=data.get("added", []),
                        removed=data.get("removed", []),
                        added_tools=data.get("added_tools", []),
                        removed_tools=data.get("removed_tools", []),
                    )
                    invalidate_runner(user_id)
                    logger.info("capability_update_during_session", user_id=user_id)
                elif msg_type == "control":
                    action = data.get("action", "")
                    if action == "voice_toggle":
                        # Acknowledged — actual modality switch is frontend-side
                        logger.info(
                            "voice_toggle", user_id=user_id, enabled=data.get("voice_enabled", True)
                        )
                elif msg_type == "mic_acquire":
                    # Explicit mic floor request — client sends this before streaming audio.
                    # Preferred over the fallback auto-acquire on first binary frame because it
                    # happens synchronously in JS before the AudioWorklet starts sending data.
                    mgr = get_connection_manager()
                    if mgr.try_acquire_mic_floor(user_id, _upstream_client_type):
                        _holds_mic_floor = True
                        _busy_notified = False
                        # Unicast "granted" via locked send so it doesn't race with
                        # relay_task or _downstream sending concurrently.
                        granted_msg = json.dumps({
                            "type": "mic_floor",
                            "event": "granted",
                            "holder": str(_upstream_client_type),
                        })
                        await mgr.send_to_client(user_id, _upstream_client_type, granted_msg)
                        # Broadcast "acquired" to ALL clients (including self) for UI state sync
                        floor_msg = json.dumps({
                            "type": "mic_floor",
                            "event": "acquired",
                            "holder": str(_upstream_client_type),
                        })
                        _fire_and_forget(mgr.send_to_user(user_id, floor_msg))
                        logger.info("mic_acquire_granted", user_id=user_id, client_type=_upstream_client_type)
                    else:
                        holder = mgr.get_mic_floor_holder(user_id)
                        denied_msg = json.dumps({
                            "type": "mic_floor",
                            "event": "denied",
                            "holder": str(holder) if holder else "unknown",
                        })
                        await mgr.send_to_client(user_id, _upstream_client_type, denied_msg)
                        logger.info("mic_acquire_denied", user_id=user_id, holder=holder)
                elif msg_type == "mic_release":
                    # Explicit release — client sends when recording stops.
                    mgr = get_connection_manager()
                    released = mgr.release_mic_floor(user_id, _upstream_client_type)
                    if released:
                        _holds_mic_floor = False
                        floor_msg = json.dumps({
                            "type": "mic_floor",
                            "event": "released",
                            "holder": str(_upstream_client_type),
                        })
                        _fire_and_forget(mgr.send_to_user(user_id, floor_msg))
                        logger.info("mic_release_explicit", user_id=user_id, client_type=_upstream_client_type)
                # Other control messages (persona_switch)
                # are handled at the API layer, not pushed to ADK
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError fires when the WS is replaced by a new connection
        logger.info("ws_upstream_disconnected", user_id=user_id)
    except Exception:
        logger.exception("ws_upstream_error", user_id=user_id)
    finally:
        queue.close()  # Signal run_live() to stop gracefully
        # Release mic floor if this connection held it, and notify other clients
        if _holds_mic_floor:
            mgr = get_connection_manager()
            released = mgr.release_mic_floor(user_id, _upstream_client_type)
            if released:
                import json as _json
                floor_msg = _json.dumps({
                    "type": "mic_floor",
                    "event": "released",
                    "holder": str(_upstream_client_type),
                })
                _fire_and_forget(mgr.send_to_user(user_id, floor_msg))


# ── Downstream (ADK → client) ────────────────────────────────────────


async def _downstream(
    websocket: WebSocket,
    runner: Runner,
    user_id: str,
    session_id: str,
    queue: LiveRequestQueue,
    run_config: RunConfig,
    client_type: str = "",
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
            await _process_event(websocket, event, bus, user_id, conn_tag=str(id(websocket)), client_type=client_type)
    except (WebSocketDisconnect, RuntimeError):
        logger.info("ws_downstream_disconnected", user_id=user_id)
    except Exception as exc:
        # Classify expected WebSocket closure conditions as info, not errors.
        exc_str = str(exc)
        exc_str_lower = exc_str.lower()

        # ADK session lost (Cloud Run cold start / new instance)
        if (
            "sessionnotfounderror" in type(exc).__name__.lower()
            or "session not found" in exc_str_lower
        ):
            logger.warning("ws_downstream_session_lost", user_id=user_id, session_id=session_id)
            # Invalidate the cache so the next reconnect creates a fresh session
            _adk_session_id_cache.pop(user_id, None)
            with contextlib.suppress(Exception):
                err = ErrorMessage(
                    code="session_expired",
                    description="Your session expired. Reconnecting…",
                )
                await websocket.send_text(err.model_dump_json())
            return  # Let the client reconnect cleanly

        normal_closure = (
            # Graceful cancel from Gemini side
            ("1000" in exc_str and "cancelled" in exc_str_lower)
            # Keepalive ping timeout — network drop between backend and Gemini
            or "keepalive ping timeout" in exc_str_lower
            # Any other normal close (1001 going away, 1006 abnormal)
            or "connection closed" in exc_str_lower
        )
        if normal_closure:
            logger.info("ws_downstream_session_ended", user_id=user_id, reason=exc_str)
        elif (
            isinstance(exc, TimeoutError)
            or "timed out" in exc_str_lower
            or "opening handshake" in exc_str_lower
        ):
            logger.warning("ws_downstream_live_timeout", user_id=user_id, error=exc_str)
            with contextlib.suppress(Exception):
                err = ErrorMessage(
                    code="live_connection_timeout",
                    description="Could not connect to the live voice service — the connection timed out. Please try again.",
                )
                await websocket.send_text(err.model_dump_json())
        elif "429" in exc_str or "resource_exhausted" in exc_str_lower:
            logger.warning("ws_downstream_rate_limited", user_id=user_id)
            with contextlib.suppress(Exception):
                err = ErrorMessage(
                    code="rate_limited",
                    description="The AI service is temporarily overloaded (rate limit). Please wait a moment and try again.",
                )
                await websocket.send_text(err.model_dump_json())
        else:
            logger.exception("ws_downstream_error", user_id=user_id)


# ── Tool classification ──────────────────────────────────────────────

# Cross-device T3 tool names (from app.tools.cross_client)
_CROSS_DEVICE_TOOLS = frozenset(
    {
        "send_to_desktop",
        "send_to_chrome",
        "send_to_dashboard",
        "notify_client",
        "list_connected_clients",
    }
)

# Native plugin tool names (from app.plugins.*)
_NATIVE_PLUGIN_TOOLS: dict[str, str] = {
    "list_calendar_events": "Google Calendar",
    "create_calendar_event": "Google Calendar",
    "delete_calendar_event": "Google Calendar",
    "search_drive_files": "Google Drive",
    "read_drive_file": "Google Drive",
    "list_drive_files": "Google Drive",
}


def _classify_tool(tool_name: str) -> tuple[ActionKind, str]:
    """Return (ActionKind, human-readable source label) for a tool name."""
    from app.tools.image_gen import IMAGE_TOOL_NAMES

    if tool_name in IMAGE_TOOL_NAMES:
        return ActionKind.IMAGE_GEN, "Image Generation"
    if tool_name in _CROSS_DEVICE_TOOLS:
        return ActionKind.CROSS_DEVICE, "Cross-Device"
    if tool_name in _NATIVE_PLUGIN_TOOLS:
        return ActionKind.NATIVE_PLUGIN, _NATIVE_PLUGIN_TOOLS[tool_name]

    # MCP tools are discovered dynamically — check the global registry.
    # If a tool isn't in any known set, check if it belongs to an MCP plugin.
    try:
        from app.services.plugin_registry import get_plugin_registry

        registry = get_plugin_registry()
        mcp_label = registry.get_tool_source(tool_name)
        if mcp_label:
            return ActionKind.MCP, mcp_label
    except Exception:
        pass

    return ActionKind.TOOL, ""


_call_id_counter = 0


_RICH_CONTENT_PATTERNS = (
    re.compile(r"```[\w]*\n", re.MULTILINE),  # fenced code blocks
    re.compile(r"^\|.+\|.+\|$", re.MULTILINE),  # markdown tables
    re.compile(r"^#{1,3} ", re.MULTILINE),  # markdown headings
    re.compile(r"^\d+\.\s.+\n\d+\.\s", re.MULTILINE),  # numbered lists (3+ items)
    re.compile(r"^- .+\n- .+\n- ", re.MULTILINE),  # bullet lists (3+ items)
)


def _has_rich_content(text: str) -> bool:
    """Return True if *text* contains content that should be rendered
    with markdown formatting (code blocks, tables, long lists, etc.).

    Used to decide whether to emit a COMPANION card alongside voice.
    """
    if len(text) < 20:
        return False
    return any(p.search(text) for p in _RICH_CONTENT_PATTERNS)


def _try_parse_genui(text: str) -> dict | None:
    """Detect structured GenUI JSON in agent text output.

    Agents can emit GenUI by returning JSON with a ``genui_type`` field:
    ``{"genui_type": "chart", "data": {...}, "text": "Here's a chart"}``

    Also detects markdown-fenced JSON blocks with genui_type.
    Returns the parsed dict on success, or None if not GenUI.
    """
    stripped = text.strip()
    # Quick reject: most text isn't GenUI
    if "genui_type" not in stripped:
        return None
    # Try direct JSON parse
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict) and obj.get("genui_type"):
            return {"type": obj["genui_type"], "data": obj.get("data", obj), "text": obj.get("text", "")}
    except (json.JSONDecodeError, ValueError):
        pass
    # Try extracting from markdown code fences
    match = re.search(r"```(?:json)?\s*\n?({.*?})\s*\n?```", stripped, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(1))
            if isinstance(obj, dict) and obj.get("genui_type"):
                return {"type": obj["genui_type"], "data": obj.get("data", obj), "text": obj.get("text", "")}
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _next_call_id(fc_id: str | None = None) -> str:
    """Generate a unique call_id for tool_call ↔ tool_response matching."""
    global _call_id_counter
    if fc_id:
        return fc_id
    _call_id_counter += 1
    return f"tc_{_call_id_counter}_{int(__import__('time').time() * 1000)}"


# Map tool_name → stack of call_ids for matching function_responses back to calls.
# Keyed by (conn_tag, tool_name). Uses a list (FIFO) so overlapping calls to the
# same tool name don't clobber each other.
_pending_call_ids: dict[tuple[str, str], list[str]] = {}


async def _process_event(
    websocket: WebSocket,
    event: Event,
    bus: EventBus | None = None,
    user_id: str = "",
    conn_tag: str = "",
    client_type: str = "",
) -> None:
    """Translate a single ADK Event into WebSocket frames.

    Non-audio JSON messages are also published to *bus* so that
    connected dashboard clients receive real-time updates.
    """
    # Stamp context vars so _publish() can embed the origin tag + client type.
    _conn_tag_var.set(conn_tag)
    _client_type_var.set(client_type)
    # ── Audio output ──────────────────────────────────────────────
    if event.content and event.content.parts:
        for part in event.content.parts:
            if part.inline_data and part.inline_data.data:
                # Raw PCM audio → binary frame (NOT forwarded to dashboard)
                await websocket.send_bytes(part.inline_data.data)
            elif part.text:
                # Detect GenUI: if the text is a JSON block with "genui_type"
                genui_payload = _try_parse_genui(part.text)
                if genui_payload:
                    msg = AgentResponse(
                        content_type=ContentType.GENUI,
                        data=genui_payload.get("text", ""),
                        genui=genui_payload,
                    )
                else:
                    msg = AgentResponse(
                        content_type=ContentType.TEXT,
                        data=part.text,
                    )
                json_str = msg.model_dump_json()
                await websocket.send_text(json_str)
                await _publish(bus, user_id, json_str)

                # Companion card: when text contains code blocks, tables,
                # or other rich content that can't be conveyed by voice alone,
                # send an additional COMPANION message so the dashboard can
                # render it with syntax highlighting / markdown.
                if not genui_payload and _has_rich_content(part.text):
                    companion = AgentResponse(
                        content_type=ContentType.COMPANION,
                        data=part.text,
                    )
                    cjson = companion.model_dump_json()
                    await websocket.send_text(cjson)
                    await _publish(bus, user_id, cjson)

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
    func_calls = event.get_function_calls()
    if func_calls:
        # Send PROCESSING status before tool execution to avoid awkward silence
        processing_msg = StatusMessage(state=AgentState.PROCESSING, detail="Using tools...")
        processing_json = processing_msg.model_dump_json()
        await websocket.send_text(processing_json)
        await _publish(bus, user_id, processing_json)

    for fc in func_calls:
        # Agent transfer → emit dedicated message instead of generic tool_call
        if fc.name == "transfer_to_agent":
            target = (fc.args or {}).get("agent_name", "")
            transfer_msg = AgentTransferMessage(
                to_agent=target,
                message=(fc.args or {}).get("message", ""),
            )
            json_str = transfer_msg.model_dump_json()
            await websocket.send_text(json_str)
            await _publish(bus, user_id, json_str)
            continue

        kind, label = _classify_tool(fc.name)
        call_id = _next_call_id(getattr(fc, "id", None))
        _pending_call_ids.setdefault((conn_tag, fc.name), []).append(call_id)
        msg = ToolCallMessage(
            call_id=call_id,
            tool_name=fc.name,
            arguments=dict(fc.args) if fc.args else {},
            status=ToolStatus.STARTED,
            action_kind=kind,
            source_label=label,
        )
        json_str = msg.model_dump_json()
        await websocket.send_text(json_str)
        await _publish(bus, user_id, json_str)

    # ── Tool responses + image delivery ─────────────────────────────
    #
    # Image tools return TEXT ONLY to Gemini (saves context tokens).
    # Actual image data is queued in ``image_gen._pending_images`` during
    # tool execution and drained here when we see the corresponding
    # function_response event.
    #
    from app.tools.image_gen import IMAGE_TOOL_NAMES, drain_pending_images

    for fr in event.get_function_responses():
        # Skip transfer_to_agent responses (already handled above)
        if fr.name == "transfer_to_agent":
            continue

        # Drain pending images queued by the tool for this user
        if fr.name in IMAGE_TOOL_NAMES and user_id:
            for img_data in drain_pending_images(user_id):
                img_msg = ImageResponseMessage(**img_data)
                json_str = img_msg.model_dump_json()
                await websocket.send_text(json_str)
                await _publish(bus, user_id, json_str)

        kind, label = _classify_tool(fr.name)
        # Recover the call_id assigned during the tool_call phase (FIFO pop)
        _id_stack = _pending_call_ids.get((conn_tag, fr.name))
        resp_call_id = (_id_stack.pop(0) if _id_stack else "") or getattr(fr, "id", "") or ""
        # Clean up empty stack entries
        if _id_stack is not None and not _id_stack:
            _pending_call_ids.pop((conn_tag, fr.name), None)
        # Always send the tool response (text summary for image tools)
        msg = ToolResponseMessage(
            tool_name=fr.name,
            result=str(fr.response) if fr.response else "",
            success=True,
            action_kind=kind,
            source_label=label,
            call_id=resp_call_id,
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
    """Publish to the event bus if available.

    Embeds ``_origin_conn`` and ``_origin_client_type`` into the JSON so that
    relay subscribers can drop their own echoes and same-device duplicates.
    """
    if bus and user_id:
        conn_tag = _conn_tag_var.get()
        ct = _client_type_var.get()
        if conn_tag or ct:
            d = json.loads(json_str)
            if conn_tag:
                d["_origin_conn"] = conn_tag
            if ct:
                d["_origin_client_type"] = ct
            json_str = json.dumps(d)
        await bus.publish(user_id, json_str)


async def _relay_cross_events(
    websocket: WebSocket,
    queue: asyncio.Queue[str],
    own_conn_tag: str,
    own_client_type: str = "",
    user_id: str = "",
    client_type: ClientType | None = None,
) -> None:
    """Forward EventBus events that did NOT originate from this connection.

    Used by ``ws_chat`` so that voice-session events from ``ws_live`` (e.g.
    a mobile caller) appear in the desktop chat panel in real-time.

    ``session_suggestion`` is forwarded (with ``cross_client: True``) so the
    dashboard can reconnect to the new session.  ``client_status_update`` is
    skipped because it is already delivered by ``/ws/events``.

    Events that originated from the SAME client_type (same device) are also
    skipped to prevent same-device duplication when both /ws/live and /ws/chat
    are open simultaneously — /ws/live already renders them directly.
    """
    _INFRA_TYPES = {"client_status_update"}
    try:
        while True:
            json_str = await queue.get()
            d = json.loads(json_str)
            if d.pop("_origin_conn", None) == own_conn_tag:
                # Own echo — already sent directly via websocket.send_text()
                continue
            if d.get("type") in _INFRA_TYPES:
                # Handled by /ws/events — don't duplicate on live/chat sockets
                continue
            origin_ct = d.pop("_origin_client_type", "")
            if own_client_type and origin_ct and origin_ct == own_client_type:
                # Same device type — /ws/live already rendered this directly;
                # skip to prevent duplication in the parallel /ws/chat relay.
                continue
            d["cross_client"] = True
            with contextlib.suppress(Exception):
                # Use the connection manager's locked send to avoid racing
                # with _upstream (mic_acquire responses) and _downstream.
                mgr = get_connection_manager()
                if user_id and client_type is not None:
                    await mgr.send_to_client(user_id, client_type, json.dumps(d))
                else:
                    lock = mgr.get_send_lock(websocket)
                    if lock:
                        async with lock:
                            await websocket.send_text(json.dumps(d))
                    else:
                        await websocket.send_text(json.dumps(d))
    except asyncio.CancelledError:
        pass


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
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
        if session is None or not session.events:
            logger.debug("vertex_persist_skip_no_events", user_id=user_id)
            return None

        # Create a new Vertex session to hold the persisted events
        vertex_session = await vertex_ss.create_session(
            app_name=APP_NAME,
            user_id=user_id,
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
    (
        user,
        client_type,
        os_name,
        requested_session_id,
        capabilities,
        local_tools,
        persona_id,
        voice_name,
    ) = auth_result

    mgr = get_connection_manager()

    # Check if OTHER client types are already online (for session continuity)
    other_clients = mgr.get_other_clients_online(user.uid, client_type)

    # Phase 2 — Register connection + store capabilities + prepare ADK session
    await mgr.connect(websocket, user.uid, client_type, os_name=os_name)
    if capabilities or local_tools:
        mgr.store_capabilities(user.uid, client_type, capabilities, local_tools)

    # Get or create the ADK session (InMemory; we cache the ID)
    active_session_service = _get_session_service()

    # ── Session resolution ────────────────────────────────────────
    # • If the client requests a specific Firestore session → resume it.
    # • If other clients are already online → reuse their session (continuity).
    # • Otherwise → create only an ADK session; the Firestore session is
    #   created lazily on first user message (no empty sessions).
    from app.services.session_service import get_session_service as _get_fs_svc

    _fs_svc = _get_fs_svc()
    firestore_session_id = None
    session_id = None
    try:
        if requested_session_id and requested_session_id != "new":
            # Client wants to resume a specific Firestore session
            fs_session = await _fs_svc.get_session(user.uid, requested_session_id)
            firestore_session_id = fs_session.id
            if fs_session.adk_session_id and await _adk_session_exists(
                fs_session.adk_session_id, user.uid, active_session_service
            ):
                session_id = fs_session.adk_session_id
                _adk_session_id_cache[user.uid] = session_id
            else:
                session_id = await _get_or_create_adk_session(
                    user.uid, active_session_service, force_new=True
                )
                await _fs_svc.link_adk_session(firestore_session_id, session_id)
        elif other_clients:
            # Other clients are online — reuse their session for continuity
            latest = await _fs_svc.get_latest_session_for_user(user.uid)
            if latest:
                firestore_session_id = latest.id
                if latest.adk_session_id and await _adk_session_exists(
                    latest.adk_session_id, user.uid, active_session_service
                ):
                    session_id = latest.adk_session_id
                    _adk_session_id_cache[user.uid] = session_id
                else:
                    session_id = await _get_or_create_adk_session(
                        user.uid, active_session_service, force_new=True
                    )
                    await _fs_svc.link_adk_session(firestore_session_id, session_id)
            else:
                # No existing session — ADK only, Firestore lazy on first message
                session_id = await _get_or_create_adk_session(user.uid, active_session_service)
        elif requested_session_id == "new":
            # User explicitly started a new chat — ADK session only,
            # Firestore session deferred to first message
            session_id = await _get_or_create_adk_session(
                user.uid, active_session_service, force_new=True
            )
        else:
            # Default: try to resume the latest session, or ADK-only
            latest = await _fs_svc.get_latest_session_for_user(user.uid)
            if latest:
                firestore_session_id = latest.id
                if latest.adk_session_id and await _adk_session_exists(
                    latest.adk_session_id, user.uid, active_session_service
                ):
                    session_id = latest.adk_session_id
                    _adk_session_id_cache[user.uid] = session_id
                else:
                    session_id = await _get_or_create_adk_session(
                        user.uid, active_session_service, force_new=True
                    )
                    await _fs_svc.link_adk_session(firestore_session_id, session_id)
            else:
                # First ever connection — ADK only, Firestore lazy
                session_id = await _get_or_create_adk_session(user.uid, active_session_service)
            logger.info("connected_to_latest_session", user_id=user.uid, firestore_session_id=firestore_session_id)
    except Exception:
        # Fallback: ensure ADK session exists
        if not session_id:
            session_id = await _get_or_create_adk_session(user.uid, active_session_service)
        # Don't create a Firestore session — leave it for lazy creation

    # Determine voice from requested voice, persona, or default
    from app.agents.personas import get_default_personas

    personas = get_default_personas()
    selected_voice = "Aoede"  # fallback
    if voice_name:
        # Client explicitly requested a voice
        selected_voice = voice_name
    elif persona_id:
        match = next((p for p in personas if p.id == persona_id), None)
        if match:
            selected_voice = match.voice
    else:
        selected_voice = personas[0].voice
    run_config = _build_run_config(voice=selected_voice)

    # Build available tool names for auth response
    from app.services.tool_registry import get_tool_registry

    tool_registry = get_tool_registry()
    available_tool_names: list[str] = []
    try:
        tools_map = await tool_registry.build_for_session(user.uid)
        for tools in tools_map.values():
            for t in tools:
                name = getattr(t, "name", getattr(t, "__name__", str(t)))
                if name not in available_tool_names:
                    available_tool_names.append(name)
    except Exception:
        logger.debug("tool_registry_preview_failed", user_id=user.uid)

    # Send auth success + connected message
    auth_ok = AuthResponse(
        status="ok", user_id=user.uid, session_id=session_id or "",
        firestore_session_id=firestore_session_id or "",
        available_tools=available_tool_names,
        other_clients_online=[str(ct) for ct in other_clients],
    )
    from starlette.websockets import WebSocketDisconnect
    connected = ConnectedMessage(session_id=session_id or "")
    try:
        await websocket.send_text(auth_ok.model_dump_json())
        await websocket.send_text(connected.model_dump_json())
    except (RuntimeError, WebSocketDisconnect) as e:
        # Handle cases where websocket disconnects during send
        logger.info("ws_send_after_close", user_id=user.uid, error=str(e))
        await mgr.disconnect(user.uid, client_type, websocket=websocket)
        return

    # If other clients are online, suggest session continuation
    if other_clients:
        from app.models.ws_messages import SessionSuggestionMessage

        suggestion = SessionSuggestionMessage(
            available_clients=[str(ct) for ct in other_clients],
            message=f"You're already active on {', '.join(str(ct) for ct in other_clients)}. Join that session for uninterrupted context?",
            session_id=firestore_session_id or "",
        )
        try:
            await websocket.send_text(suggestion.model_dump_json())
        except (RuntimeError, WebSocketDisconnect):
            logger.info("ws_send_after_close", user_id=user.uid)
            await mgr.disconnect(user.uid, client_type, websocket=websocket)
            return

    # Phase 3 — Bidi streaming
    from google.adk.agents.live_request_queue import LiveRequestQueue

    queue = LiveRequestQueue()
    runner = await _get_runner(user.uid, session_service=active_session_service)

    # Subscribe to EventBus so events from other sessions (e.g. /ws/chat or another /ws/live)
    # are forwarded to this connection in real-time.
    bus = get_event_bus()
    own_conn_tag = str(id(websocket))
    cross_queue = bus.create_queue()
    bus.subscribe(user.uid, cross_queue)
    relay_task = asyncio.create_task(
        _relay_cross_events(
            websocket, cross_queue, own_conn_tag,
            own_client_type=str(client_type),
            user_id=user.uid,
            client_type=client_type,
        ),
        name=f"live_relay_{own_conn_tag}",
    )

    # Broadcast session creation/resumption so idle devices can auto-join
    if firestore_session_id:
        session_msg = {
            "type": "session_suggestion",
            "session_id": firestore_session_id,
            "available_clients": [str(client_type)],
            "message": f"Session active on {client_type}.",
            "_origin_conn": own_conn_tag,
            "_origin_client_type": str(client_type),
        }
        _fire_and_forget(bus.publish(user.uid, json.dumps(session_msg)))

    logger.info(
        "live_session_ready",
        user_id=user.uid,
        session_id=session_id,
        client_type=str(client_type),
    )

    up_task: asyncio.Task | None = None
    down_task: asyncio.Task | None = None
    fs_id_ref = [firestore_session_id]
    try:
        up_task = asyncio.create_task(
            _upstream(websocket, queue, user.uid, client_type, firestore_session_id_ref=fs_id_ref, conn_tag=own_conn_tag, adk_session_id=session_id),
            name="upstream",
        )
        # Only start downstream (agent runner) if we have a valid session_id
        if session_id:
            down_task = asyncio.create_task(
                _downstream(websocket, runner, user.uid, session_id, queue, run_config, client_type=str(client_type)),
                name="downstream",
            )
            tasks = {up_task, down_task}
        else:
            tasks = {up_task}
        # When either task finishes (disconnect or error), cancel the other
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        # Await pending tasks to let them clean up
        await asyncio.gather(*pending, return_exceptions=True)
        # Re-raise if the completed task had an unexpected exception
        for task in done:
            if task.exception() and not isinstance(task.exception(), asyncio.CancelledError):
                logger.warning(
                    "ws_task_error",
                    user_id=user.uid,
                    task=task.get_name(),
                    exc_info=task.exception(),
                )
    except asyncio.CancelledError:
        logger.info("ws_live_cancelled", user_id=user.uid)
    except Exception:
        logger.exception("ws_live_error", user_id=user.uid)
    finally:
        # Cancel cross-client relay and unsubscribe from EventBus
        relay_task.cancel()
        bus.unsubscribe(user.uid, cross_queue)

        # Phase 4 — Cleanup
        queue.close()  # Ensure queue is closed (upstream also closes, but be safe)

        # Persist session to Vertex AI first so memory sync can reference it.
        # Memory generation requires a valid Vertex AI session resource name.
        vertex_session_id: str | None = None
        if settings.USE_AGENT_ENGINE_SESSIONS:
            vertex_session_id = await _background_persist_to_vertex(
                user.uid,
                session_id,
                active_session_service,
            )

        # Generate memories from the Vertex session (not the InMemory one)
        if vertex_session_id:
            try:
                await get_memory_service().sync_from_session(user.uid, vertex_session_id)
            except Exception as exc:
                exc_str = str(exc).lower()
                if "throttled" in exc_str or "quota" in exc_str or "resource_exhausted" in exc_str:
                    logger.debug(
                        "memory_bank_sync_throttled", user_id=user.uid, session_id=session_id
                    )
                else:
                    logger.warning(
                        "memory_bank_sync_failed",
                        user_id=user.uid,
                        session_id=session_id,
                        exc_info=True,
                    )

        await mgr.disconnect(user.uid, client_type, websocket=websocket)
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
    from google.genai import types

    await websocket.accept()

    auth_result = await _authenticate_ws(websocket)
    if auth_result is None:
        return
    (
        user,
        client_type,
        _os_name,
        requested_session_id,
        capabilities,
        local_tools,
        _persona_id,
        _voice,
    ) = auth_result

    mgr = get_connection_manager()

    # Register as auxiliary socket so this WS receives client_status_update broadcasts
    aux_key = f"chat_{id(websocket)}"
    mgr.add_aux_socket(user.uid, aux_key, websocket)

    active_session_service = _get_session_service()
    session_id = await _get_or_create_adk_session(user.uid, active_session_service)

    # Store capabilities if provided
    if capabilities or local_tools:
        mgr.store_capabilities(user.uid, client_type, capabilities, local_tools)

    # Link Firestore session to ADK session — lazy creation on first message
    from app.services.session_service import get_session_service as _get_fs_svc

    _fs_svc = _get_fs_svc()
    firestore_session_id = None
    try:
        if requested_session_id and requested_session_id != "new":
            # Client wants to resume a specific Firestore session
            fs_session = await _fs_svc.get_session(user.uid, requested_session_id)
            firestore_session_id = fs_session.id
            if not fs_session.adk_session_id:
                await _fs_svc.link_adk_session(firestore_session_id, session_id)
        elif requested_session_id != "new":
            # Check if there's an existing session to resume
            latest = await _fs_svc.get_latest_session_for_user(user.uid)
            if latest and latest.adk_session_id == session_id:
                firestore_session_id = latest.id
            # Otherwise: firestore_session_id stays None → lazy creation on first message
    except Exception:
        pass  # Firestore session deferred to first user message

    auth_ok = AuthResponse(
        status="ok",
        user_id=user.uid,
        session_id=session_id,
        firestore_session_id=firestore_session_id or "",
    )
    await websocket.send_text(auth_ok.model_dump_json())

    # Send current client status so the dashboard is up-to-date immediately
    clients = mgr.get_connected_clients(user.uid)
    if clients:
        import json as _json

        status_payload = _json.dumps(
            {
                "type": "client_status_update",
                "event": "snapshot",
                "client_type": "web",
                "clients": [
                    {
                        "client_type": str(c.client_type),
                        "client_id": c.client_id,
                        "connected_at": c.connected_at.isoformat() if c.connected_at else None,
                        "os_name": c.os_name,
                        "connected": True,
                    }
                    for c in clients
                ],
            }
        )
        with contextlib.suppress(Exception):
            await websocket.send_text(status_payload)

    bus = get_event_bus()
    runner = await _get_chat_runner(user.uid, session_service=active_session_service)

    # Subscribe to EventBus so events from other sessions (e.g. /ws/live on
    # mobile) are forwarded to this dashboard connection in real-time.
    own_conn_tag = str(id(websocket))
    cross_queue = bus.create_queue()
    bus.subscribe(user.uid, cross_queue)
    relay_task = asyncio.create_task(
        _relay_cross_events(websocket, cross_queue, own_conn_tag, own_client_type=str(client_type)),
        name=f"chat_relay_{own_conn_tag}",
    )

    logger.info("ws_chat_connected", user_id=user.uid, session_id=session_id)

    _first_message_in_chat = True
    _active_turn: asyncio.Task | None = None  # currently running run_async turn
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if data.get("type") != "text" or not data.get("content", "").strip():
                continue

            user_text = data["content"]
            content = types.Content(
                parts=[types.Part(text=user_text)],
                role="user",
            )

            # Lazy Firestore session creation on first user message
            if _first_message_in_chat and not firestore_session_id:
                _fs_ref = [None]
                await _lazy_create_firestore_session(
                    _fs_ref, user.uid, session_id, websocket, user_text
                )
                firestore_session_id = _fs_ref[0]
                _first_message_in_chat = False
            elif _first_message_in_chat and firestore_session_id:
                _first_message_in_chat = False
                _fire_and_forget(
                    _fs_svc.generate_title_from_message(firestore_session_id, user_text)
                )

            # Publish user text to EventBus for cross-client sync
            if bus and user.uid:
                user_msg = {
                    "type": "user_message",
                    "content": user_text,
                    "_origin_conn": own_conn_tag,
                    "_origin_client_type": str(client_type) if client_type else "",
                }
                _fire_and_forget(bus.publish(user.uid, json.dumps(user_msg)))

            # Increment message count
            if firestore_session_id:
                _fire_and_forget(_increment_msg_count(firestore_session_id))

            # Cancel any in-flight turn so the new message takes priority
            if _active_turn and not _active_turn.done():
                _active_turn.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await _active_turn
                # Let the user know the previous turn was interrupted
                interrupt_msg = StatusMessage(state=AgentState.IDLE, detail="Interrupted — processing new message")
                with contextlib.suppress(Exception):
                    await websocket.send_text(interrupt_msg.model_dump_json())

            # Status: thinking
            thinking_msg = StatusMessage(state=AgentState.PROCESSING)
            await websocket.send_text(thinking_msg.model_dump_json())

            # Run the ADK turn in a background task so the receive loop stays responsive.
            # This allows the user to send a new message while a tool is running.
            async def _run_turn(_content=content):
                try:
                    async for event in runner.run_async(
                        user_id=user.uid,
                        session_id=session_id,
                        new_message=_content,
                    ):
                        await _process_event(websocket, event, bus, user.uid, conn_tag=own_conn_tag, client_type=str(client_type))
                    # run_async events don't carry turn_complete, so send IDLE explicitly
                    idle_msg = StatusMessage(state=AgentState.IDLE)
                    await websocket.send_text(idle_msg.model_dump_json())
                except asyncio.CancelledError:
                    raise  # Let cancellation propagate cleanly
                except Exception as turn_exc:
                    turn_exc_str = str(turn_exc)
                    turn_exc_lower = turn_exc_str.lower()
                    if "429" in turn_exc_str or "resource_exhausted" in turn_exc_lower:
                        logger.warning("ws_chat_turn_rate_limited", user_id=user.uid)
                        err_msg = ErrorMessage(
                            code="rate_limited",
                            description="The AI service is temporarily overloaded (rate limit). Please wait a moment and try again.",
                        )
                        await websocket.send_text(err_msg.model_dump_json())
                    elif "timed out" in turn_exc_lower or isinstance(turn_exc, TimeoutError):
                        logger.warning("ws_chat_turn_timeout", user_id=user.uid)
                        err_msg = ErrorMessage(
                            code="request_timeout",
                            description="The request to the AI service timed out. Please try again.",
                        )
                        await websocket.send_text(err_msg.model_dump_json())
                    else:
                        logger.exception("ws_chat_turn_error", user_id=user.uid)
                        err_msg = ErrorMessage(
                            code="agent_error",
                            description="Something went wrong processing your message. Please try again.",
                        )
                        await websocket.send_text(err_msg.model_dump_json())
                    # Always return to IDLE so the client re-enables input
                    await websocket.send_text(StatusMessage(state=AgentState.IDLE).model_dump_json())

            _active_turn = asyncio.create_task(_run_turn(), name=f"chat_turn_{own_conn_tag}")

    except (WebSocketDisconnect, RuntimeError):
        logger.info("ws_chat_disconnected", user_id=user.uid)
    except Exception:
        logger.exception("ws_chat_error", user_id=user.uid)
    finally:
        # Cancel cross-client relay and unsubscribe from EventBus
        relay_task.cancel()
        bus.unsubscribe(user.uid, cross_queue)

        # Remove auxiliary socket registration
        mgr.remove_aux_socket(user.uid, aux_key)

        # Persist chat session to Vertex + generate memories (same as ws_live)
        vertex_session_id: str | None = None
        if settings.USE_AGENT_ENGINE_SESSIONS:
            vertex_session_id = await _background_persist_to_vertex(
                user.uid,
                session_id,
                active_session_service,
            )
        if vertex_session_id:
            try:
                await get_memory_service().sync_from_session(user.uid, vertex_session_id)
            except Exception:
                logger.warning("memory_bank_sync_failed_chat", user_id=user.uid, exc_info=True)

        logger.info("ws_chat_closed", user_id=user.uid, session_id=session_id)
