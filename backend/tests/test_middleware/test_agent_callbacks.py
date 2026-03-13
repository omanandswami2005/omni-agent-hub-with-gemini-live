"""Tests for ADK agent callbacks — context injection, cost estimation,
permission checking, and after-agent lifecycle hooks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.middleware.agent_callbacks import (
    after_agent_callback,
    before_agent_callback,
    context_injection_callback,
    cost_estimation_callback,
    permission_check_callback,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _make_ctx(**state_items) -> MagicMock:
    """Build a mock ADK Context with a mutable .state dict."""
    ctx = MagicMock()
    ctx.state = dict(state_items)
    ctx.agent_name = "test_agent"
    return ctx


def _make_llm_request(system_instruction: str = "") -> MagicMock:
    req = MagicMock()
    req.config = MagicMock()
    req.config.system_instruction = system_instruction
    return req


def _make_llm_response(text: str = "", usage: dict | None = None) -> MagicMock:
    resp = MagicMock()
    part = MagicMock()
    part.text = text
    resp.content = MagicMock()
    resp.content.parts = [part]
    resp.content.text = text
    if usage:
        resp.usage_metadata = MagicMock()
        resp.usage_metadata.prompt_token_count = usage.get("prompt", 0)
        resp.usage_metadata.candidates_token_count = usage.get("candidates", 0)
    else:
        resp.usage_metadata = None
    return resp


def _make_tool(name: str) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    return tool


# ── 1. Context injection ─────────────────────────────────────────────


class TestContextInjection:
    def test_no_state_returns_none(self):
        ctx = _make_ctx()
        req = _make_llm_request("existing instruction")
        result = context_injection_callback(ctx, req)
        assert result is None
        # instruction unchanged
        assert req.config.system_instruction == "existing instruction"

    def test_injects_user_preferences(self):
        ctx = _make_ctx(user_preferences="dark mode, metric units")
        req = _make_llm_request("base")
        result = context_injection_callback(ctx, req)
        assert result is None
        assert "dark mode, metric units" in req.config.system_instruction
        assert "base" in req.config.system_instruction

    def test_injects_session_memory(self):
        ctx = _make_ctx(session_memory="User asked about weather earlier")
        req = _make_llm_request("")
        context_injection_callback(ctx, req)
        assert "weather" in req.config.system_instruction

    def test_injects_persona_context(self):
        ctx = _make_ctx(persona_context="You are a coder persona")
        req = _make_llm_request("")
        context_injection_callback(ctx, req)
        assert "coder persona" in req.config.system_instruction

    def test_injects_all_three(self):
        ctx = _make_ctx(
            user_preferences="pref1",
            session_memory="mem1",
            persona_context="ctx1",
        )
        req = _make_llm_request("base")
        context_injection_callback(ctx, req)
        instr = req.config.system_instruction
        assert "pref1" in instr
        assert "mem1" in instr
        assert "ctx1" in instr
        assert "base" in instr


# ── 2. Cost estimation ───────────────────────────────────────────────


class TestCostEstimation:
    def test_estimates_from_text_length(self):
        ctx = _make_ctx()
        resp = _make_llm_response("a" * 400)  # ~100 tokens
        result = cost_estimation_callback(ctx, resp)
        assert result is None
        cost = ctx.state["_cost"]
        assert cost["output_tokens"] > 0
        assert cost["calls"] == 1

    def test_uses_usage_metadata_when_available(self):
        ctx = _make_ctx()
        resp = _make_llm_response("hi", usage={"prompt": 50, "candidates": 10})
        cost_estimation_callback(ctx, resp)
        cost = ctx.state["_cost"]
        assert cost["input_tokens"] == 50
        assert cost["output_tokens"] == 10

    def test_accumulates_across_calls(self):
        ctx = _make_ctx()
        resp1 = _make_llm_response("hi", usage={"prompt": 10, "candidates": 5})
        resp2 = _make_llm_response("bye", usage={"prompt": 20, "candidates": 8})
        cost_estimation_callback(ctx, resp1)
        cost_estimation_callback(ctx, resp2)
        cost = ctx.state["_cost"]
        assert cost["input_tokens"] == 30
        assert cost["output_tokens"] == 13
        assert cost["calls"] == 2
        assert cost["usd"] > 0


# ── 3. Permission checking ──────────────────────────────────────────


class TestPermissionChecking:
    def test_allows_non_destructive_tools(self):
        ctx = _make_ctx()
        tool = _make_tool("search")
        result = permission_check_callback(tool, {}, ctx)
        assert result is None

    def test_blocks_destructive_without_permission(self):
        ctx = _make_ctx()
        tool = _make_tool("send_email")
        result = permission_check_callback(tool, {}, ctx)
        assert result is not None
        assert "error" in result
        assert "destructive" in result["error"]

    def test_allows_destructive_with_explicit_permission(self):
        ctx = _make_ctx(permissions_granted={"send_email"})
        tool = _make_tool("send_email")
        result = permission_check_callback(tool, {}, ctx)
        assert result is None

    def test_allows_destructive_with_wildcard(self):
        ctx = _make_ctx(permissions_granted={"*"})
        tool = _make_tool("delete_file")
        result = permission_check_callback(tool, {}, ctx)
        assert result is None

    def test_blocks_multiple_destructive_tools(self):
        ctx = _make_ctx()
        for tool_name in ["delete_file", "send_email", "manage_files", "drop_table"]:
            tool = _make_tool(tool_name)
            result = permission_check_callback(tool, {}, ctx)
            assert result is not None, f"{tool_name} should be blocked"


# ── 4. After-agent callback ─────────────────────────────────────────


class TestAfterAgentCallback:
    def test_before_agent_sets_start_timestamp(self):
        ctx = _make_ctx()
        result = before_agent_callback(ctx)
        assert result is None
        assert "_agent_start_ts" in ctx.state

    def test_after_agent_logs_completion(self):
        import time

        ctx = _make_ctx(_agent_start_ts=time.monotonic() - 1.0)
        result = after_agent_callback(ctx)
        assert result is None
        summary = ctx.state["_last_agent_summary"]
        assert summary["agent"] == "test_agent"
        assert summary["elapsed_s"] is not None
        assert summary["elapsed_s"] >= 0.9

    @patch("app.services.event_bus.EventBus")
    def test_after_agent_publishes_event(self, mock_bus_cls):
        import time

        mock_bus = MagicMock()
        mock_bus_cls.get_default.return_value = mock_bus

        ctx = _make_ctx(
            _agent_start_ts=time.monotonic(),
            user_id="user-42",
        )
        after_agent_callback(ctx)
        mock_bus.publish.assert_called_once()
        call_args = mock_bus.publish.call_args
        assert call_args[0][0] == "user-42"
        assert call_args[0][1]["type"] == "agent_completed"
