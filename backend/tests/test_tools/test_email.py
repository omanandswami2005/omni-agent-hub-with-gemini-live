"""Tests for the stub email tool."""

import pytest

from app.tools.email import get_email_tools, send_email, send_email_tool


@pytest.fixture()
def mock_tool_context():
    from unittest.mock import MagicMock

    ctx = MagicMock()
    ctx.user_id = "test-user-456"
    return ctx


class TestSendEmail:
    @pytest.mark.asyncio
    async def test_returns_confirmation(self, mock_tool_context):
        result = await send_email(
            to="user@example.com",
            subject="Grocery List",
            body="Milk, Eggs, Bread",
            tool_context=mock_tool_context,
        )
        assert "Email sent successfully" in result
        assert "user@example.com" in result
        assert "Grocery List" in result

    @pytest.mark.asyncio
    async def test_includes_body_length(self, mock_tool_context):
        body = "A" * 100
        result = await send_email(
            to="a@b.com",
            subject="test",
            body=body,
            tool_context=mock_tool_context,
        )
        assert "100 chars" in result

    @pytest.mark.asyncio
    async def test_works_without_tool_context(self):
        result = await send_email(to="a@b.com", subject="s", body="b")
        assert "Email sent successfully" in result

    @pytest.mark.asyncio
    async def test_stub_marker_present(self, mock_tool_context):
        result = await send_email(
            to="a@b.com",
            subject="s",
            body="b",
            tool_context=mock_tool_context,
        )
        assert "Stub" in result


class TestFunctionToolInstances:
    def test_send_email_tool_is_function_tool(self):
        from google.adk.tools import FunctionTool

        assert isinstance(send_email_tool, FunctionTool)

    def test_get_email_tools_returns_list(self):
        tools = get_email_tools()
        assert len(tools) == 1

    def test_communication_capability_provides_email(self):
        from app.agents.agent_factory import get_tools_for_capabilities

        tools = get_tools_for_capabilities(["communication"])
        names = [getattr(t, "name", getattr(t, "__name__", "")) for t in tools]
        assert "send_email" in names
