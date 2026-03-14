"""ADK agent callbacks — context injection, cost estimation, permission
checking, and after-agent lifecycle hooks.

These callbacks are wired into every ADK ``Agent`` at creation time via
``agent_factory.create_agent()`` and ``root_agent.build_root_agent()``.

ADK callback signatures (google.adk 0.5+ — all keyword arguments):
  before_model_callback(callback_context=, llm_request=) → LlmResponse | None
  after_model_callback(callback_context=, llm_response=) → LlmResponse | None
  before_tool_callback(tool=, args=, tool_context=)     → dict | None
  after_tool_callback(tool=, args=, tool_context=, tool_response=) → dict | None
  before_agent_callback(callback_context=, **kwargs)    → Content | None
  after_agent_callback(callback_context=, **kwargs)     → Content | None
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from app.utils.logging import get_logger

if TYPE_CHECKING:
    from google.adk.agents.context import Context
    from google.adk.models.llm_response import LlmResponse
    from google.genai.types import Content

logger = get_logger(__name__)

# ── Destructive tools that require permission ─────────────────────────
# Tool names (T1/T2/T3) that destroy data or send external messages.
_DESTRUCTIVE_TOOLS: frozenset[str] = frozenset(
    {
        "delete_file",
        "remove_file",
        "manage_files",
        "send_email",
        "send_gmail",
        "file_delete",
        "drop_table",
    }
)


def _get_state(ctx: Context) -> dict[str, Any]:
    """Return the mutable state dict from the ADK context."""
    s = getattr(ctx, "state", None)
    if s is None:
        return {}
    return s


# ---------------------------------------------------------------------------
# 1. Context injection — before_model_callback
# ---------------------------------------------------------------------------


def context_injection_callback(
    callback_context=None,
    llm_request=None,
    **kwargs,
) -> LlmResponse | None:
    """Prepend user preferences, session memory, and persona-specific
    system context before every model call.

    Reads from ``ctx.state`` which is populated by the WebSocket handler
    or REST endpoint before the runner starts.
    """
    ctx = callback_context
    state = _get_state(ctx)

    # Collect context fragments
    fragments: list[str] = []

    # User preferences (set at session start from Firestore profile)
    user_prefs = state.get("user_preferences")
    if user_prefs:
        fragments.append(f"[User preferences]: {user_prefs}")

    # Session memory — rolling summary of what happened so far
    session_memory = state.get("session_memory")
    if session_memory:
        fragments.append(f"[Session memory]: {session_memory}")

    # Persona-specific context (e.g. "You are a coder persona that …")
    persona_ctx = state.get("persona_context")
    if persona_ctx:
        fragments.append(f"[Persona context]: {persona_ctx}")

    if not fragments:
        return None  # nothing to inject

    injection = "\n".join(fragments)
    logger.debug("context_injected", agent=getattr(ctx, "agent_name", "?"), length=len(injection))

    # Prepend to the system instruction in the LlmRequest
    if llm_request.config and hasattr(llm_request.config, "system_instruction"):
        current = llm_request.config.system_instruction or ""
        llm_request.config.system_instruction = f"{injection}\n\n{current}"

    return None  # proceed with (mutated) request


# ---------------------------------------------------------------------------
# 2. Cost estimation — after_model_callback
# ---------------------------------------------------------------------------

# Rough per-token costs (USD) for Gemini 2.5 Flash (Vertex AI pricing).
# These are estimates — real billing comes from the API usage dashboard.
_INPUT_COST_PER_TOKEN = 0.000_000_15  # $0.15 per 1M input tokens
_OUTPUT_COST_PER_TOKEN = 0.000_000_60  # $0.60 per 1M output tokens


def _estimate_tokens(text: str) -> int:
    """Estimate token count from text length (≈4 chars/token for English)."""
    return max(1, len(text) // 4)


def cost_estimation_callback(
    callback_context=None,
    llm_response=None,
    **kwargs,
) -> LlmResponse | None:
    """Log estimated token counts and cost after every model response.

    Stores running totals in ``ctx.state["_cost"]`` so callers can read
    cumulative usage at session end.
    """
    ctx = callback_context
    text = ""
    if hasattr(llm_response, "content") and llm_response.content:
        content = llm_response.content
        if hasattr(content, "parts"):
            text = " ".join(getattr(p, "text", "") or "" for p in content.parts)
        elif hasattr(content, "text"):
            text = content.text or ""

    output_tokens = _estimate_tokens(text)

    # Try to get actual usage metadata from the response
    usage = getattr(llm_response, "usage_metadata", None)
    if usage:
        input_tokens = getattr(usage, "prompt_token_count", 0) or 0
        actual_output = getattr(usage, "candidates_token_count", 0) or 0
        if actual_output:
            output_tokens = actual_output
    else:
        input_tokens = 0

    estimated_cost = input_tokens * _INPUT_COST_PER_TOKEN + output_tokens * _OUTPUT_COST_PER_TOKEN

    # Accumulate in state
    state = _get_state(ctx)
    cost_state = state.get("_cost", {"input_tokens": 0, "output_tokens": 0, "usd": 0.0, "calls": 0})
    cost_state["input_tokens"] += input_tokens
    cost_state["output_tokens"] += output_tokens
    cost_state["usd"] += estimated_cost
    cost_state["calls"] += 1
    state["_cost"] = cost_state

    logger.info(
        "cost_estimate",
        agent=getattr(ctx, "agent_name", "?"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_usd=round(estimated_cost, 8),
        cumulative_usd=round(cost_state["usd"], 6),
        total_calls=cost_state["calls"],
    )

    return None  # proceed


# ---------------------------------------------------------------------------
# 3. Permission checking — before_tool_callback
# ---------------------------------------------------------------------------


def permission_check_callback(
    tool=None,
    args=None,
    tool_context=None,
    **kwargs,
) -> dict | None:
    """Block destructive tools unless the user has explicitly granted
    permission (``ctx.state["permissions_granted"]`` is a set/list of
    tool names or ``"*"``).
    """
    ctx = tool_context
    tool_name = getattr(tool, "name", "")
    if tool_name not in _DESTRUCTIVE_TOOLS:
        return None  # non-destructive → allow

    state = _get_state(ctx)
    granted = state.get("permissions_granted", set())

    if "*" in granted or tool_name in granted:
        return None  # explicitly allowed

    logger.warning(
        "tool_blocked",
        tool=tool_name,
        reason="destructive tool requires permission",
    )
    return {
        "error": (
            f"Tool '{tool_name}' is destructive and requires explicit "
            f"permission.  Grant permission by setting "
            f"permissions_granted in your session state."
        ),
    }


# ---------------------------------------------------------------------------
# 4. After-agent callback — auto-summarize, emit events, cleanup
# ---------------------------------------------------------------------------


def after_agent_callback(callback_context=None, **kwargs) -> Content | None:
    """Fires when a sub-agent completes.

    - Logs a completion event with elapsed time.
    - Stores a short summary in ``ctx.state["_last_agent_summary"]``.
    - Publishes a completion event to the EventBus (if available).
    """
    ctx = callback_context
    agent_name = getattr(ctx, "agent_name", "unknown")
    start_ts = _get_state(ctx).get("_agent_start_ts")
    elapsed = round(time.monotonic() - start_ts, 3) if start_ts else None

    logger.info(
        "agent_completed",
        agent=agent_name,
        elapsed_s=elapsed,
    )

    # Store a summary marker so upstream agents can read it
    state = _get_state(ctx)
    state["_last_agent_summary"] = {
        "agent": agent_name,
        "completed_at": time.time(),
        "elapsed_s": elapsed,
    }

    # Try to emit an EventBus event (non-critical)
    try:
        from app.services.event_bus import EventBus

        user_id = state.get("user_id")
        if user_id:
            EventBus.get_default().publish(
                user_id,
                {
                    "type": "agent_completed",
                    "agent": agent_name,
                    "elapsed_s": elapsed,
                },
            )
    except Exception:
        pass  # EventBus not available is fine

    return None  # don't inject extra content


def before_agent_callback(callback_context=None, **kwargs) -> Content | None:
    """Record the start timestamp so ``after_agent_callback`` can compute
    elapsed time."""
    ctx = callback_context
    state = _get_state(ctx)
    state["_agent_start_ts"] = time.monotonic()
    return None
