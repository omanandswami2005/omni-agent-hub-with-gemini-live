"""Tests for Cross-Client Action Tools (Task 12)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.client import ClientInfo, ClientType
from app.services.connection_manager import ConnectionManager
from app.tools.cross_client import (
    get_cross_client_tools,
    list_connected_clients,
    notify_client,
    send_to_chrome,
    send_to_dashboard,
    send_to_desktop,
)
from app.tools.desktop_tools import (
    desktop_screenshot,
    desktop_click,
    desktop_type,
    desktop_launch,
    get_desktop_tools,
)

_NOW = datetime.now(tz=UTC)

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def mock_cm():
    """Return a mock ConnectionManager."""
    cm = MagicMock(spec=ConnectionManager)
    cm.is_online = MagicMock(return_value=True)
    cm.send_to_client = AsyncMock()
    cm.get_connected_clients = MagicMock(
        return_value=[
            ClientInfo(
                user_id="u1",
                client_type=ClientType.WEB,
                client_id="u1:web",
                connected_at=_NOW,
                last_ping=_NOW,
            ),
            ClientInfo(
                user_id="u1",
                client_type=ClientType.DESKTOP,
                client_id="u1:desktop",
                connected_at=_NOW,
                last_ping=_NOW,
            ),
        ]
    )
    return cm


@pytest.fixture(autouse=True)
def _reset_cm_singleton():
    """Reset connection_manager singleton."""
    import app.services.connection_manager as mod

    old = mod._manager
    mod._manager = None
    yield
    mod._manager = old


def _fake_ctx(user_id: str = "u1") -> MagicMock:
    """Create a mock ToolContext with a user_id."""
    ctx = MagicMock()
    ctx.user_id = user_id
    return ctx


# ── send_to_desktop ──────────────────────────────────────────────────


class TestSendToDesktop:
    @pytest.mark.asyncio
    async def test_delivers_when_online(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await send_to_desktop("open_app", '{"app": "calc"}', tool_context=_fake_ctx())
        assert result["delivered"] is True
        mock_cm.send_to_client.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fails_when_offline(self, mock_cm):
        mock_cm.is_online.return_value = False
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await send_to_desktop("open_app", "{}", tool_context=_fake_ctx())
        assert result["delivered"] is False
        assert "not connected" in result["error"]


class TestSendToChrome:
    @pytest.mark.asyncio
    async def test_delivers(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await send_to_chrome("open_tab", '{"url": "https://x.com"}', tool_context=_fake_ctx())
        assert result["delivered"] is True

    @pytest.mark.asyncio
    async def test_sends_correct_client_type(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            await send_to_chrome("get_page", "{}", tool_context=_fake_ctx())
        args = mock_cm.send_to_client.call_args
        assert args[0][1] == ClientType.CHROME


class TestSendToDashboard:
    @pytest.mark.asyncio
    async def test_delivers(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await send_to_dashboard("show_notification", '{"msg": "hi"}', tool_context=_fake_ctx())
        assert result["delivered"] is True


class TestNotifyClient:
    @pytest.mark.asyncio
    async def test_sends_notification(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await notify_client("Hello!", "web", tool_context=_fake_ctx())
        assert result["delivered"] is True

    @pytest.mark.asyncio
    async def test_invalid_client_type(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await notify_client("Hello!", "invalid_type", tool_context=_fake_ctx())
        assert result["delivered"] is False
        assert "Unknown client type" in result["error"]


class TestListConnectedClients:
    @pytest.mark.asyncio
    async def test_returns_clients(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await list_connected_clients(tool_context=_fake_ctx())
        assert len(result["clients"]) == 2
        types = {c["client_type"] for c in result["clients"]}
        assert ClientType.WEB in types
        assert ClientType.DESKTOP in types


# ── Message format ───────────────────────────────────────────────────


class TestMessageFormat:
    @pytest.mark.asyncio
    async def test_message_has_correct_structure(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            await send_to_desktop("capture_screen", '{"format": "png"}', tool_context=_fake_ctx())
        sent_msg = mock_cm.send_to_client.call_args[0][2]
        parsed = json.loads(sent_msg)
        assert parsed["type"] == "cross_client"
        assert parsed["action"] == "capture_screen"
        assert parsed["data"]["format"] == "png"


# ── Desktop tools (E2B-based) ────────────────────────────────────────


class TestDesktopTools:
    """Desktop tools now use E2B service, not cross-client relay."""

    def test_desktop_tools_are_importable(self):
        assert callable(desktop_screenshot)
        assert callable(desktop_click)
        assert callable(desktop_type)
        assert callable(desktop_launch)


# ── FunctionTool instances ───────────────────────────────────────────


class TestFunctionToolInstances:
    def test_cross_client_tools_count(self):
        tools = get_cross_client_tools()
        assert len(tools) == 5

    def test_cross_client_tool_names(self):
        tools = get_cross_client_tools()
        names = {t.name for t in tools}
        assert "send_to_desktop" in names
        assert "send_to_chrome" in names
        assert "send_to_dashboard" in names
        assert "notify_client" in names
        assert "list_connected_clients" in names

    def test_desktop_tools_count(self):
        tools = get_desktop_tools()
        assert len(tools) == 20

    def test_desktop_tool_names(self):
        tools = get_desktop_tools()
        names = {t.name for t in tools}
        assert "desktop_screenshot" in names
        assert "desktop_click" in names
        assert "desktop_type" in names
        assert "desktop_launch" in names
        assert "desktop_bash" in names
        assert "start_desktop" in names


# ── Agent factory integration ────────────────────────────────────────


class TestAgentFactoryIntegration:
    def test_all_personas_get_cross_client_tools(self):
        from app.agents.agent_factory import _default_tools_for_persona

        for pid in ("assistant", "coder", "researcher", "analyst", "creative"):
            tools = _default_tools_for_persona(pid)
            names = {t.name for t in tools}
            assert "send_to_desktop" in names, f"{pid} missing send_to_desktop"
            assert "list_connected_clients" in names, f"{pid} missing list_connected_clients"
