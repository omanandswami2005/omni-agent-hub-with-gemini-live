"""Multimodal-aware AgentTool that forwards cached user images.

Standard ``AgentTool`` only passes the text ``request`` parameter when
delegating to a sub-agent.  This subclass checks the per-user image cache
(populated by ``ws_live.py``) and injects the most recent image as an
additional ``types.Part(inline_data=…)`` in the Content sent to the
sub-agent, so the model can actually *see* uploaded images.

.. note::

   ``run_async`` is overridden because the parent constructs Content
   internally with no extension hook.  Mirrors ADK ≥1.26 logic — if
   you upgrade ADK, verify the base ``AgentTool.run_async`` hasn't
   changed substantially.
"""

from __future__ import annotations

from typing import Any

from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.tools._forwarding_artifact_service import ForwardingArtifactService
from google.adk.tools.agent_tool import AgentTool, _get_input_schema, _get_output_schema
from google.adk.tools.tool_context import ToolContext
from google.adk.utils.context_utils import Aclosing
from google.genai import types

from app.utils.image_cache import pop_user_image
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MultimodalAgentTool(AgentTool):
    """AgentTool that injects cached user images into sub-agent requests."""

    async def run_async(
        self,
        *,
        args: dict[str, Any],
        tool_context: ToolContext,
    ) -> Any:
        from google.adk.runners import Runner
        from google.adk.sessions.in_memory_session_service import (
            InMemorySessionService,
        )

        if self.skip_summarization:
            tool_context.actions.skip_summarization = True

        # ── Build Content — same as parent but with optional image Part ──
        input_schema = _get_input_schema(self.agent)
        if input_schema:
            input_value = input_schema.model_validate(args)
            parts: list[types.Part] = [
                types.Part.from_text(
                    text=input_value.model_dump_json(exclude_none=True)
                )
            ]
        else:
            parts = [types.Part.from_text(text=args["request"])]

        # Inject cached user image as a native image Part
        user_id = tool_context._invocation_context.user_id
        cached_blob = pop_user_image(user_id) if user_id else None
        if cached_blob:
            parts.append(types.Part(inline_data=cached_blob))
            logger.info(
                "image_injected_into_agent_tool",
                agent=self.name,
                user_id=user_id,
                mime_type=cached_blob.mime_type,
                image_size=len(cached_blob.data),
            )

        content = types.Content(role="user", parts=parts)

        # ── Runner setup (mirrors parent) ────────────────────────────
        invocation_context = tool_context._invocation_context
        parent_app_name = (
            invocation_context.app_name if invocation_context else None
        )
        child_app_name = parent_app_name or self.agent.name
        plugins = (
            invocation_context.plugin_manager.plugins
            if self.include_plugins
            else None
        )
        runner = Runner(
            app_name=child_app_name,
            agent=self.agent,
            artifact_service=ForwardingArtifactService(tool_context),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
            credential_service=invocation_context.credential_service,
            plugins=plugins,
        )

        state_dict = {
            k: v
            for k, v in tool_context.state.to_dict().items()
            if not k.startswith("_adk")
        }
        session = await runner.session_service.create_session(
            app_name=child_app_name,
            user_id=invocation_context.user_id,
            state=state_dict,
        )

        # ── Run sub-agent ────────────────────────────────────────────
        last_content = None
        async with Aclosing(
            runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=content,
            )
        ) as agen:
            async for event in agen:
                if event.actions.state_delta:
                    tool_context.state.update(event.actions.state_delta)
                if event.content:
                    last_content = event.content

        await runner.close()

        if last_content is None or last_content.parts is None:
            return ""
        merged_text = "\n".join(
            p.text for p in last_content.parts if p.text and not p.thought
        )
        output_schema = _get_output_schema(self.agent)
        if output_schema:
            return output_schema.model_validate_json(merged_text).model_dump(
                exclude_none=True
            )
        return merged_text
