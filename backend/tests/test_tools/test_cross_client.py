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
    capture_screen,
    click_at,
    get_desktop_tools,
    open_application,
    type_text,
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


# ── send_to_desktop ──────────────────────────────────────────────────


class TestSendToDesktop:
    @pytest.mark.asyncio
    async def test_delivers_when_online(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await send_to_desktop("u1", "open_app", '{"app": "calc"}')
        assert result["delivered"] is True
        mock_cm.send_to_client.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fails_when_offline(self, mock_cm):
        mock_cm.is_online.return_value = False
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await send_to_desktop("u1", "open_app", "{}")
        assert result["delivered"] is False
        assert "not connected" in result["error"]


class TestSendToChrome:
    @pytest.mark.asyncio
    async def test_delivers(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await send_to_chrome("u1", "open_tab", '{"url": "https://x.com"}')
        assert result["delivered"] is True

    @pytest.mark.asyncio
    async def test_sends_correct_client_type(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            await send_to_chrome("u1", "get_page", "{}")
        args = mock_cm.send_to_client.call_args
        assert args[0][1] == ClientType.CHROME


class TestSendToDashboard:
    @pytest.mark.asyncio
    async def test_delivers(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await send_to_dashboard("u1", "show_notification", '{"msg": "hi"}')
        assert result["delivered"] is True


class TestNotifyClient:
    @pytest.mark.asyncio
    async def test_sends_notification(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await notify_client("u1", "Hello!", "web")
        assert result["delivered"] is True

    @pytest.mark.asyncio
    async def test_invalid_client_type(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await notify_client("u1", "Hello!", "invalid_type")
        assert result["delivered"] is False
        assert "Unknown client type" in result["error"]


class TestListConnectedClients:
    @pytest.mark.asyncio
    async def test_returns_clients(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await list_connected_clients("u1")
        assert len(result["clients"]) == 2
        types = {c["client_type"] for c in result["clients"]}
        assert ClientType.WEB in types
        assert ClientType.DESKTOP in types


# ── Message format ───────────────────────────────────────────────────


class TestMessageFormat:
    @pytest.mark.asyncio
    async def test_message_has_correct_structure(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            await send_to_desktop("u1", "capture_screen", '{"format": "png"}')
        sent_msg = mock_cm.send_to_client.call_args[0][2]
        parsed = json.loads(sent_msg)
        assert parsed["type"] == "cross_client_action"
        assert parsed["action"] == "capture_screen"
        assert parsed["payload"]["format"] == "png"


# ── Desktop tools ────────────────────────────────────────────────────


class TestDesktopTools:
    @pytest.mark.asyncio
    async def test_capture_screen(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await capture_screen("u1")
        assert result["delivered"] is True

    @pytest.mark.asyncio
    async def test_click_at(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await click_at("u1", 100, 200)
        assert result["delivered"] is True
        sent = json.loads(mock_cm.send_to_client.call_args[0][2])
        assert sent["payload"]["x"] == 100
        assert sent["payload"]["y"] == 200

    @pytest.mark.asyncio
    async def test_type_text(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await type_text("u1", "hello world")
        assert result["delivered"] is True
        sent = json.loads(mock_cm.send_to_client.call_args[0][2])
        assert sent["payload"]["text"] == "hello world"

    @pytest.mark.asyncio
    async def test_open_application(self, mock_cm):
        with patch("app.tools.cross_client.get_connection_manager", return_value=mock_cm):
            result = await open_application("u1", "calculator")
        assert result["delivered"] is True
        sent = json.loads(mock_cm.send_to_client.call_args[0][2])
        assert sent["payload"]["app_name"] == "calculator"


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
        assert len(tools) == 6

    def test_desktop_tool_names(self):
        tools = get_desktop_tools()
        names = {t.name for t in tools}
        assert "capture_screen" in names
        assert "click_at" in names
        assert "type_text" in names
        assert "open_application" in names
        assert "manage_files" in names
        assert "press_key" in names


# ── Agent factory integration ────────────────────────────────────────


class TestAgentFactoryIntegration:
    def test_all_personas_get_cross_client_tools(self):
        from app.agents.agent_factory import _default_tools_for_persona

        for pid in ("assistant", "coder", "researcher", "analyst", "creative"):
            tools = _default_tools_for_persona(pid)
            names = {t.name for t in tools}
            assert "send_to_desktop" in names, f"{pid} missing send_to_desktop"
            assert "list_connected_clients" in names, f"{pid} missing list_connected_clients"
