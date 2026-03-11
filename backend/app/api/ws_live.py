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


def _get_session_service():
    """Lazy singleton: build the ADK session service on first access.

    When ``USE_AGENT_ENGINE_SESSIONS`` is *True* (requires Vertex AI),
    uses ``VertexAiSessionService`` backed by Agent Engine — failures are
    **not** silently swallowed so misconfigurations surface immediately.

    When *False*, uses ``InMemorySessionService`` (local dev / offline).
    """
    global _adk_session_service
    if _adk_session_service is not None:
        return _adk_session_service

    if not settings.USE_AGENT_ENGINE_SESSIONS:
        from google.adk.sessions import InMemorySessionService
        _adk_session_service = InMemorySessionService()
        logger.info("session_service_init", backend="in_memory")
        return _adk_session_service

    # Vertex AI path — fail loudly on misconfiguration
    from google.adk.sessions import VertexAiSessionService
    from app.services.agent_engine_service import get_agent_engine_service

    ae = get_agent_engine_service()
    agent_engine_id = ae.get_reasoning_engine_id()
    _adk_session_service = VertexAiSessionService(
        project=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.GOOGLE_CLOUD_LOCATION,
        agent_engine_id=agent_engine_id,
    )
    logger.info(
        "session_service_init",
        backend="vertex_ai",
        project=settings.GOOGLE_CLOUD_PROJECT,
        agent_engine_id=agent_engine_id,
    )
    return _adk_session_service


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


async def _authenticate_ws(websocket: WebSocket) -> tuple[AuthenticatedUser, ClientType] | None:
    """Wait for the first JSON frame and validate it as an auth message.

    Returns ``(AuthenticatedUser, client_type)`` on success, or ``None`` after sending
    an error and closing the socket.
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
        decoded = firebase_auth.verify_id_token(data["token"])
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

    logger.info("ws_auth_ok", uid=decoded.get("uid"), client=client_type_str)
    
    return AuthenticatedUser(decoded), client_type


async def _send_auth_error(websocket: WebSocket, error: str) -> None:
    msg = AuthResponse(status="error", error=error)
    await websocket.send_text(msg.model_dump_json())
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
                    queue.send_content(
                        types.Content(
                            parts=[types.Part(inline_data=blob)],
                            role="user",
                        )
                    )
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
    except Exception:
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

    for fr in event.get_function_responses():
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


# ── Main WebSocket endpoint ──────────────────────────────────────────


@router.websocket("/live")
async def ws_live(websocket: WebSocket) -> None:
    """Bidirectional audio streaming with Gemini via ADK."""
    await websocket.accept()

    # Phase 1 — Authenticate (includes client_type detection)
    auth_result = await _authenticate_ws(websocket)
    if auth_result is None:
        return
    user, client_type = auth_result

    mgr = get_connection_manager()
    
    # Check if OTHER client types are already online (for session continuity)
    other_clients = mgr.get_other_clients_online(user.uid, client_type)
    
    # Phase 2 — Register connection + prepare ADK session
    await mgr.connect(websocket, user.uid, client_type)
    
    # Use a unified session ID for cross-device continuity
    # All devices share the same session for this user
    session_id = f"{user.uid}_main"

    # Ensure ADK session exists — no silent fallback; misconfiguration must surface
    active_session_service = _get_session_service()
    session = await active_session_service.get_session(
        app_name=APP_NAME, user_id=user.uid, session_id=session_id,
    )
    if session is None:
        await active_session_service.create_session(
            app_name=APP_NAME, user_id=user.uid, session_id=session_id,
        )

    # Determine voice from active persona (default: first default persona)
    from app.agents.personas import get_default_personas
    default_persona = get_default_personas()[0]
    run_config = _build_run_config(voice=default_persona.voice)

    # Send auth success + connected message
    auth_ok = AuthResponse(status="ok", user_id=user.uid, session_id=session_id)
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
        try:
            await get_memory_service().sync_from_session(user.uid, session_id)
        except Exception:
            logger.warning("memory_bank_sync_failed", user_id=user.uid, session_id=session_id, exc_info=True)

        await mgr.disconnect(user.uid, client_type)
        logger.info("ws_live_closed", user_id=user.uid, session_id=session_id)
