"""CRUD /sessions + message retrieval from ADK session events."""

import contextlib

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
    with contextlib.suppress(Exception):
        session = await inmem.get_session(
            app_name=APP_NAME,
            user_id=user.uid,
            session_id=adk_sid,
        )

    # Fall back to Vertex AI (persisted sessions)
    if session is None or not session.events:
        vertex_ss = _get_vertex_session_service()
        if vertex_ss:
            with contextlib.suppress(Exception):
                session = await vertex_ss.get_session(
                    app_name=APP_NAME,
                    user_id=user.uid,
                    session_id=adk_sid,
                )

    if session is None or not session.events:
        return []

    messages = await _events_to_messages(session.events)

    # Always sync message_count to actual count (including 0 after redeploy)
    with contextlib.suppress(Exception):
        await svc.update_message_count(session_id, len(messages))

    return messages


async def _gcs_uri_to_https(gcs_uri: str) -> str:
    """Convert a gs://bucket/path URI to a browseable HTTPS URL.

    Tries to generate a signed URL first; falls back to the public HTTPS URL.
    Returns the original string unchanged if it is not a gs:// URI.
    """
    if not gcs_uri or not gcs_uri.startswith("gs://"):
        return gcs_uri  # already an HTTPS URL or empty
    import asyncio as _asyncio

    from app.services.storage_service import get_storage_service
    # gs://bucket-name/path/to/file  →  path/to/file
    parts = gcs_uri[5:].split("/", 1)  # strip "gs://"
    bucket = parts[0]
    path = parts[1] if len(parts) > 1 else ""
    svc = get_storage_service()
    try:
        return await _asyncio.to_thread(svc.generate_signed_url, path, expiry_minutes=60)
    except Exception:
        # Fallback: public HTTPS URL (works if bucket/object is public)
        return f"https://storage.googleapis.com/{bucket}/{path}"


async def _events_to_messages(events: list) -> list[ChatMessage]:
    """Convert ADK session events into a flat list of chat messages.

    Extracts:
    - Finished input transcriptions → user voice messages
    - Finished output transcriptions → assistant voice messages
    - Text content with role=user → user text messages
    - Text content with role=model → assistant text messages
    - Function calls → system action messages (with full metadata)
    - Function responses → system action messages (with result + status)
    - state_delta → GenUI results and image results (from AgentTool personas)
    """
    import json as _json

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

        # Tool responses — merge into the matching tool_call entry above
        # instead of creating a second ActionCard for the same invocation.
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

            # For image tools, emit a separate image message (not an action)
            if is_image_tool and response_dict:
                # Mark the matching tool_call entry as responded so it
                # doesn't render as an infinite-spinner dangling card.
                for i in range(len(messages) - 1, -1, -1):
                    m = messages[i]
                    if m.type == "action" and m.tool_name == fr.name and not m.responded:
                        m.responded = True
                        m.success = True
                        m.result = "Image generated — see below"
                        break
                # generate_image: {"image_url": "gs://...", "description": "...", "mime_type": "..."}
                # generate_rich_image: {"text_summary": "...", "image_parts": [{"gcs_uri": ..., "mime_type": ...}]}
                if fr.name == "generate_rich_image":
                    text_summary = response_dict.get("text_summary", result_str)
                    raw_image_parts = response_dict.get("image_parts", [])
                    # Convert gcs_uris to HTTPS URLs
                    parts = [{"type": "text", "content": text_summary}] if text_summary else []
                    for ip in raw_image_parts:
                        url = await _gcs_uri_to_https(ip.get("gcs_uri", ""))
                        if url:
                            parts.append({"type": "image", "image_url": url, "mime_type": ip.get("mime_type", "image/png")})
                    messages.append(
                        ChatMessage(
                            role="assistant",
                            content=text_summary,
                            type="image",
                            tool_name=fr.name,
                            description=text_summary,
                            parts=parts,
                            responded=True,
                            success=True,
                            action_kind=kind,
                            source_label=label,
                        )
                    )
                else:
                    # generate_image
                    raw_url = response_dict.get("image_url") or response_dict.get("gcs_uri") or ""
                    image_url = await _gcs_uri_to_https(raw_url)
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
                # Non-image tool: merge result into the matching tool_call entry
                # (walk backwards to find the unresponded action for this tool)
                merged = False
                for i in range(len(messages) - 1, -1, -1):
                    m = messages[i]
                    if (
                        m.type == "action"
                        and m.tool_name == fr.name
                        and not m.responded
                    ):
                        m.result = result_str
                        m.success = True
                        m.responded = True
                        merged = True
                        break
                # Fallback: no matching call found (shouldn't happen in practice)
                if not merged:
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

        # ── state_delta: GenUI + image results from AgentTool personas ──
        # After the AgentTool migration, tool calls (images, GenUI) happen
        # inside the persona's isolated session.  The persona writes results
        # into session state which AgentTool forwards as state_delta on the
        # root event.  We extract those here for history replay.
        if event.actions and getattr(event.actions, "state_delta", None):
            _delta = event.actions.state_delta

            # GenUI results (accumulated list from render_genui_component)
            _genui_raw = _delta.get("_genui_results")
            if _genui_raw:
                try:
                    _genui_list = _json.loads(_genui_raw) if isinstance(_genui_raw, str) else _genui_raw
                    if isinstance(_genui_list, list):
                        for gi in _genui_list:
                            messages.append(
                                ChatMessage(
                                    role="assistant",
                                    content=gi.get("text", ""),
                                    type="text",
                                    content_type="genui",
                                    genui_type=gi.get("type", ""),
                                    genui_data=gi.get("data"),
                                )
                            )
                except (_json.JSONDecodeError, TypeError):
                    pass

            # Image results (accumulated list from generate_image / generate_rich_image)
            _img_raw = _delta.get("_image_results")
            if _img_raw:
                try:
                    _img_list = _json.loads(_img_raw) if isinstance(_img_raw, str) else _img_raw
                    if isinstance(_img_list, list):
                        for ii in _img_list:
                            tool_name = ii.get("tool_name", "generate_image")
                            if tool_name == "generate_rich_image":
                                # Interleaved text+image parts
                                raw_parts = ii.get("parts", [])
                                converted_parts = []
                                for rp in raw_parts:
                                    if rp.get("type") == "text":
                                        converted_parts.append(rp)
                                    elif rp.get("type") == "image":
                                        url = await _gcs_uri_to_https(rp.get("image_url", ""))
                                        converted_parts.append({"type": "image", "image_url": url, "mime_type": rp.get("mime_type", "image/png")})
                                messages.append(
                                    ChatMessage(
                                        role="assistant",
                                        content=ii.get("text", ""),
                                        type="image",
                                        tool_name=tool_name,
                                        description=ii.get("text", ""),
                                        parts=converted_parts,
                                    )
                                )
                            else:
                                # Single image (generate_image)
                                url = await _gcs_uri_to_https(ii.get("image_url", ""))
                                messages.append(
                                    ChatMessage(
                                        role="assistant",
                                        content=ii.get("description", ""),
                                        type="image",
                                        tool_name=tool_name,
                                        description=ii.get("description", ""),
                                        image_url=url,
                                    )
                                )
                except (_json.JSONDecodeError, TypeError):
                    pass

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
