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
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agents.personas import get_default_personas
from app.agents.root_agent import build_root_agent
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
from app.services.agent_engine_service import get_agent_engine_service
from app.services.connection_manager import get_connection_manager
from app.services.event_bus import EventBus, get_event_bus
from app.services.memory_service import get_memory_service
from app.services.mcp_manager import get_mcp_manager
from app.utils.logging import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

router = APIRouter()

# ── Module-level singletons (initialised lazily) ─────────────────────


def _build_adk_session_service():
    if not settings.USE_AGENT_ENGINE_SESSIONS:
        return InMemorySessionService()

    try:
        from google.adk.sessions import VertexAiSessionService

        ae = get_agent_engine_service()
        agent_engine_id = ae.get_reasoning_engine_id()
        return VertexAiSessionService(
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,
            agent_engine_id=agent_engine_id,
        )
    except Exception:
        logger.warning("vertex_ai_session_service_init_failed_fallback_in_memory", exc_info=True)
        return InMemorySessionService()


_adk_session_service = _build_adk_session_service()
APP_NAME = "omni-hub"

AUDIO_INPUT_MIME = "audio/pcm;rate=16000"


async def _get_runner(user_id: str) -> Runner:
    """Create a runner with user-specific MCP tools.
    
    Each user gets their own runner instance with their enabled MCP tools.
    """
    mcp_mgr = get_mcp_manager()
    mcp_tools: list = []
    try:
        mcp_tools = await mcp_mgr.get_tools(user_id)
    except Exception:
        logger.warning("mcp_tools_load_failed", user_id=user_id, exc_info=True)
    
    root = build_root_agent(mcp_tools=mcp_tools)
    return Runner(
        app_name=APP_NAME,
        agent=root,
        session_service=_adk_session_service,
    )


def _build_run_config(voice: str = "Aoede") -> RunConfig:
    """Build an ADK ``RunConfig`` for bidi live streaming."""
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
        session_resumption=types.SessionResumptionConfig(),
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

    # Parse client_type from message, default to WEB
    client_type_str = data.get("client_type", "web").lower()
    try:
        client_type = ClientType(client_type_str)
    except ValueError:
        client_type = ClientType.WEB

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
                    content = types.Content(
                        parts=[types.Part(inline_data=blob)],
                        role="user",
                    )
                    queue.send_content(content)
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
                            logger.info("mcp_toggle_during_session", user_id=user_id, mcp_id=mcp_id, enabled=enabled)
                        except Exception:
                            logger.warning("mcp_toggle_failed", user_id=user_id, mcp_id=mcp_id, exc_info=True)
                # Other control messages (persona_switch)
                # are handled at the API layer, not pushed to ADK
    except WebSocketDisconnect:
        logger.info("ws_upstream_disconnected", user_id=user_id)
    except Exception:
        logger.exception("ws_upstream_error", user_id=user_id)


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
    try:
        async for event in runner.run_live(
            user_id=user_id,
            session_id=session_id,
            live_request_queue=queue,
            run_config=run_config,
        ):
            await _process_event(websocket, event, bus, user_id)
    except WebSocketDisconnect:
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
    user, client_type = await _authenticate_ws(websocket)
    if user is None:
        return

    mgr = get_connection_manager()
    
    # Check if OTHER client types are already online (for session continuity)
    other_clients = mgr.get_other_clients_online(user.uid, client_type)
    
    # Phase 2 — Register connection + prepare ADK session
    await mgr.connect(websocket, user.uid, client_type)
    
    # Use a unified session ID for cross-device continuity
    # All devices share the same session for this user
    session_id = f"{user.uid}_main"

    # Ensure ADK session exists
    session = await _adk_session_service.get_session(
        app_name=APP_NAME, user_id=user.uid, session_id=session_id,
    )
    if session is None:
        await _adk_session_service.create_session(
            app_name=APP_NAME, user_id=user.uid, session_id=session_id,
        )

    # Determine voice from active persona (default: first default persona)
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
    queue = LiveRequestQueue()
    runner = await _get_runner(user.uid)

    try:
        await asyncio.gather(
            _upstream(websocket, queue, user.uid),
            _downstream(websocket, runner, user.uid, session_id, queue, run_config),
            return_exceptions=True,
        )
    except Exception:
        logger.exception("ws_live_error", user_id=user.uid)
    finally:
        # Phase 4 — Cleanup
        try:
            await get_memory_service().sync_from_session(user.uid, session_id)
        except Exception:
            logger.warning("memory_bank_sync_failed", user_id=user.uid, session_id=session_id, exc_info=True)

        queue.close()
        await mgr.disconnect(user.uid, ClientType.WEB)
        logger.info("ws_live_closed", user_id=user.uid, session_id=session_id)
