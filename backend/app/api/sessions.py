"""CRUD /sessions + message retrieval from ADK session events."""

from fastapi import APIRouter, Depends

from app.middleware.auth_middleware import CurrentUser
from app.models.session import (
    ChatMessage,
    SessionCreate,
    SessionListItem,
    SessionResponse,
    SessionUpdate,
)
from app.services.session_service import SessionService, get_session_service

router = APIRouter()


@router.post("", status_code=201)
async def create_session(
    body: SessionCreate,
    user: CurrentUser,
    svc: SessionService = Depends(get_session_service),  # noqa: B008
) -> SessionResponse:
    """Create a new conversation session."""
    return await svc.create_session(user.uid, body)


@router.get("")
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


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    user: CurrentUser,
    svc: SessionService = Depends(get_session_service),  # noqa: B008
) -> list[ChatMessage]:
    """Return chat messages by reading ADK session events.

    Tries InMemorySessionService first (fast, current process),
    then falls back to VertexAiSessionService (persisted across restarts).

    Also updates message_count in Firestore to stay in sync.
    """
    fs_session = await svc.get_session(user.uid, session_id)
    adk_sid = fs_session.adk_session_id
    if not adk_sid:
        return []

    from app.api.ws_live import APP_NAME, _get_session_service, _get_vertex_session_service

    # Try InMemory first (zero-latency, available while server is running)
    inmem = _get_session_service()
    session = None
    try:
        session = await inmem.get_session(
            app_name=APP_NAME,
            user_id=user.uid,
            session_id=adk_sid,
        )
    except Exception:
        pass

    # Fall back to Vertex AI (persisted sessions)
    if session is None or not session.events:
        vertex_ss = _get_vertex_session_service()
        if vertex_ss:
            try:
                session = await vertex_ss.get_session(
                    app_name=APP_NAME,
                    user_id=user.uid,
                    session_id=adk_sid,
                )
            except Exception:
                pass

    if session is None or not session.events:
        return []

    messages = _events_to_messages(session.events)

    # Update message_count in Firestore to stay in sync with actual message count
    if messages:
        try:
            await svc.update_message_count(session_id, len(messages))
        except Exception:
            pass  # Non-critical - silently ignore

    return messages


def _events_to_messages(events: list) -> list[ChatMessage]:
    """Convert ADK session events into a flat list of chat messages.

    Extracts:
    - Finished input transcriptions → user voice messages
    - Finished output transcriptions → assistant voice messages
    - Text content with role=user → user text messages
    - Text content with role=model → assistant text messages
    - Function calls → system action messages (with full metadata)
    - Function responses → system action messages (with result + status)
    """
    from app.api.ws_live import _classify_tool
    from app.tools.image_gen import IMAGE_TOOL_NAMES as _IMAGE_TOOL_NAMES

    messages: list[ChatMessage] = []

    for event in events:
        # User text input (from ws_chat run_async)
        if event.content and event.content.role == "user" and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text and part.text.strip():
                    messages.append(
                        ChatMessage(
                            role="user",
                            content=part.text.strip(),
                            type="text",
                            source="text",
                        )
                    )

        # Agent text response
        if event.content and event.content.role == "model" and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text and part.text.strip():
                    messages.append(
                        ChatMessage(
                            role="assistant",
                            content=part.text.strip(),
                            type="text",
                            source="text",
                        )
                    )

        # Finished voice transcriptions
        if (
            event.input_transcription
            and getattr(event.input_transcription, "finished", False)
            and event.input_transcription.text
            and event.input_transcription.text.strip()
        ):
            messages.append(
                ChatMessage(
                    role="user",
                    content=event.input_transcription.text.strip(),
                    type="text",
                    source="voice",
                )
            )

        if (
            event.output_transcription
            and getattr(event.output_transcription, "finished", False)
            and event.output_transcription.text
            and event.output_transcription.text.strip()
        ):
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=event.output_transcription.text.strip(),
                    type="text",
                    source="voice",
                )
            )

        # Tool calls
        for fc in event.get_function_calls():
            if fc.name == "transfer_to_agent":
                messages.append(
                    ChatMessage(
                        role="system",
                        content=f"Transferring to {(fc.args or {}).get('agent_name', '')}",
                        type="action",
                        tool_name="transfer_to_agent",
                        action_kind="agent_transfer",
                        responded=True,
                        success=True,
                    )
                )
                continue

            kind, label = _classify_tool(fc.name)
            messages.append(
                ChatMessage(
                    role="system",
                    content=f"Using tool: {fc.name}",
                    type="action",
                    tool_name=fc.name,
                    arguments=dict(fc.args) if fc.args else {},
                    action_kind=kind,
                    source_label=label,
                )
            )

        # Tool responses
        for fr in event.get_function_responses():
            if fr.name == "transfer_to_agent":
                continue

            kind, label = _classify_tool(fr.name)
            # Check if this is an image tool
            is_image_tool = fr.name in _IMAGE_TOOL_NAMES

            # Extract response as dict if possible
            response_dict = None
            if (fr.response and hasattr(fr.response, "get")) or (
                fr.response and isinstance(fr.response, dict)
            ):
                response_dict = fr.response

            result_str = str(fr.response) if fr.response else f"Tool {fr.name} completed"

            # For image tools, emit an image message with URL so the UI can show the image
            if is_image_tool and response_dict:
                image_url = response_dict.get("image_url") or response_dict.get("gcs_uri") or ""
                # Only emit the image message, not the action (avoid duplicate)
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=result_str,
                        type="image",
                        tool_name=fr.name,
                        description=response_dict.get("description", result_str),
                        image_url=image_url,
                        responded=True,
                        success=True,
                        action_kind=kind,
                        source_label=label,
                    )
                )
            else:
                # For non-image tools, emit action message
                messages.append(
                    ChatMessage(
                        role="system",
                        content=result_str,
                        type="action",
                        tool_name=fr.name,
                        result=result_str,
                        success=True,
                        responded=True,
                        action_kind=kind,
                        source_label=label,
                    )
                )

    return messages


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
