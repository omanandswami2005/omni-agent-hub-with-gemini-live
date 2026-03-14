"""Tests for the desktop computer-use ADK tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.tools.desktop_tools import (
    capture_screen,
    click_at,
    get_desktop_tools,
    manage_files,
    open_application,
    press_key,
    type_text,
)

_SEND = "app.tools.desktop_tools._send_action"


class TestCaptureScreen:
    @pytest.mark.asyncio
    @patch(_SEND, new_callable=AsyncMock, return_value={"delivered": True})
    async def test_sends_action(self, mock_send):
        result = await capture_screen(user_id="u1")
        assert result == {"delivered": True}
        mock_send.assert_awaited_once()
        assert mock_send.call_args[0][2] == "capture_screen"


class TestClickAt:
    @pytest.mark.asyncio
    @patch(_SEND, new_callable=AsyncMock, return_value={"delivered": True})
    async def test_sends_coordinates(self, mock_send):
        result = await click_at(user_id="u1", x=100, y=200)
        assert result["delivered"] is True
        payload = mock_send.call_args[0][3]
        assert "100" in payload
        assert "200" in payload


class TestTypeText:
    @pytest.mark.asyncio
    @patch(_SEND, new_callable=AsyncMock, return_value={"delivered": True})
    async def test_sends_text(self, mock_send):
        result = await type_text(user_id="u1", text="hello")
        assert result["delivered"] is True
        payload = mock_send.call_args[0][3]
        assert "hello" in payload


class TestOpenApplication:
    @pytest.mark.asyncio
    @patch(_SEND, new_callable=AsyncMock, return_value={"delivered": True})
    async def test_sends_app_name(self, mock_send):
        result = await open_application(user_id="u1", app_name="notepad")
        assert result["delivered"] is True
        payload = mock_send.call_args[0][3]
        assert "notepad" in payload


class TestManageFiles:
    @pytest.mark.asyncio
    @patch(_SEND, new_callable=AsyncMock, return_value={"delivered": True})
    async def test_read_action(self, mock_send):
        result = await manage_files(user_id="u1", action="read", path="/tmp/f.txt")
        assert result["delivered"] is True
        assert mock_send.call_args[0][2] == "manage_files"

    @pytest.mark.asyncio
    @patch(_SEND, new_callable=AsyncMock, return_value={"delivered": True})
    async def test_write_action(self, mock_send):
        result = await manage_files(user_id="u1", action="write", path="/tmp/f.txt", content="data")
        assert result["delivered"] is True

    @pytest.mark.asyncio
    @patch(_SEND, new_callable=AsyncMock, return_value={"delivered": True})
    async def test_list_action(self, mock_send):
        result = await manage_files(user_id="u1", action="list", path="/tmp")
        assert result["delivered"] is True

    @pytest.mark.asyncio
    @patch(_SEND, new_callable=AsyncMock, return_value={"delivered": True})
    async def test_delete_action(self, mock_send):
        result = await manage_files(user_id="u1", action="delete", path="/tmp/f.txt")
        assert result["delivered"] is True

    @pytest.mark.asyncio
    async def test_invalid_action_rejected(self):
        result = await manage_files(user_id="u1", action="hack", path="/etc/passwd")
        assert result["delivered"] is False
        assert "error" in result


class TestPressKey:
    @pytest.mark.asyncio
    @patch(_SEND, new_callable=AsyncMock, return_value={"delivered": True})
    async def test_sends_key_combo(self, mock_send):
        result = await press_key(user_id="u1", key_combo="ctrl+c")
        assert result["delivered"] is True
        payload = mock_send.call_args[0][3]
        assert "ctrl+c" in payload

    @pytest.mark.asyncio
    @patch(_SEND, new_callable=AsyncMock, return_value={"delivered": True})
    async def test_single_key(self, mock_send):
        result = await press_key(user_id="u1", key_combo="enter")
        assert result["delivered"] is True


class TestGetDesktopTools:
    def test_returns_six_tools(self):
        tools = get_desktop_tools()
        assert len(tools) == 6

    def test_tool_names(self):
        tools = get_desktop_tools()
        names = {t.name for t in tools}
        assert "capture_screen" in names
        assert "manage_files" in names
        assert "press_key" in names
